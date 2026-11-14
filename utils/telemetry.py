"""Nonblocking tracing and bounded-cardinality application instrumentation."""

import asyncio
import inspect
import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial, wraps
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from prometheus_client import Counter, Gauge, Histogram

from config import observability as settings
from utils.logger import logger

tracer = trace.get_tracer("jntuh.observability")
propagator = TraceContextTextMapPropagator()
_trace_provider = None
_configured = False
_function_outcome = ContextVar("function_outcome", default=None)

OPERATIONS = Counter(
    "backend_operations_total", "Completed backend operations.", ("operation", "status")
)
OPERATION_DURATION = Histogram(
    "backend_operation_duration_seconds", "Backend operation latency.", ("operation",),
    buckets=(0.005, 0.025, 0.1, 0.5, 1, 5, 15, 60, 300, 1800),
)
OPERATIONS_IN_PROGRESS = Gauge(
    "backend_operations_in_progress", "Active backend operations.", ("operation",)
)


class _ObservedSpan:
    def __init__(self, span):
        self.span = span
        self.failed = False

    def set_status(self, status):
        self.failed = status == StatusCode.ERROR
        self.span.set_status(status)

    def set_attribute(self, name, value):
        self.span.set_attribute(name, value)


def configure_telemetry(role):
    global _configured, _trace_provider
    if _configured:
        return
    _configured = True
    if settings.OTEL_ENABLED and settings.OTEL_TRACES_ENDPOINT:
        resource = Resource.create({
            "service.name": f"{settings.OTEL_SERVICE_NAME}-{role}",
            "service.namespace": "jntuh",
            "deployment.environment": settings.OTEL_ENVIRONMENT,
        })
        # Preserve explicit standard OTel sampler settings. Otherwise sample
        # roots at 10% and honor the parent decision across API/worker processes.
        sampler = None if os.getenv("OTEL_TRACES_SAMPLER") else ParentBased(
            TraceIdRatioBased(settings.OTEL_TRACE_SAMPLE_RATIO)
        )
        _trace_provider = TracerProvider(resource=resource, sampler=sampler)
        _trace_provider.add_span_processor(BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.OTEL_TRACES_ENDPOINT, timeout=3),
            max_queue_size=settings.OTEL_SPAN_QUEUE_SIZE,
            max_export_batch_size=settings.OTEL_SPAN_BATCH_SIZE,
            schedule_delay_millis=settings.OTEL_SPAN_SCHEDULE_DELAY,
        ))
        trace.set_tracer_provider(_trace_provider)
    # Access logs include raw query strings; the ASGI middleware logs templates.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True


def shutdown_telemetry():
    global _trace_provider
    if _trace_provider is not None:
        _trace_provider.shutdown()
        _trace_provider = None


@contextmanager
def operation(name, *, kind=SpanKind.INTERNAL, context=None, attributes=None):
    start = time.perf_counter()
    status = "success"
    OPERATIONS_IN_PROGRESS.labels(name).inc()
    with tracer.start_as_current_span(
        name, kind=kind, context=context, attributes=attributes,
        record_exception=False, set_status_on_exception=False,
    ) as span:
        observed = _ObservedSpan(span)
        try:
            yield observed
            if observed.failed:
                status = "error"
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except BaseException as error:
            status = "error"
            # Types only: exception messages may contain student data or URLs.
            span.set_attribute("error.type", type(error).__name__)
            span.set_status(StatusCode.ERROR)
            raise
        finally:
            OPERATIONS.labels(name, status).inc()
            OPERATION_DURATION.labels(name).observe(time.perf_counter() - start)
            OPERATIONS_IN_PROGRESS.labels(name).dec()


def observe(name, *, false_is_error=False, none_is_error=False):
    """Observe async boundaries without recording arguments or response data."""
    def decorate(function):
        attributes = _function_attributes(function)
        @wraps(function)
        async def wrapped(*args, **kwargs):
            with operation(name, attributes=attributes) as span:
                result = await function(*args, **kwargs)
                if ((false_is_error and result is False)
                        or (none_is_error and result is None)
                        or (isinstance(result, dict) and result.get("status") == "failed")):
                    span.set_status(StatusCode.ERROR)
                return result
        wrapped.__jntuh_traced__ = True
        return wrapped
    return decorate


def _function_attributes(function):
    return {
        "code.function.name": function.__qualname__,
        "code.namespace": function.__module__,
        "code.line.number": function.__code__.co_firstlineno,
    }


def log_failure(operation_name, error, *, event_logger=logger, level=logging.ERROR):
    """Record a failure's type and operation, without exception messages or data."""
    span = trace.get_current_span()
    span.set_attribute("error.type", type(error).__name__)
    span.set_status(StatusCode.ERROR)
    outcome = _function_outcome.get()
    if outcome is not None:
        outcome.update(failed=True, logged=True, level=level)
    event_logger.log(level, "Operation failed", extra={
        "operation": operation_name, "error_type": type(error).__name__,
        "outcome": "error",
    })


def _record_function_result(result):
    outcome = _function_outcome.get()
    if outcome is None:
        return
    status_code = getattr(result, "status_code", None)
    if isinstance(status_code, int) and status_code >= 400:
        outcome.update(failed=True, level=logging.ERROR if status_code >= 500 else logging.WARNING)
    elif isinstance(result, dict) and (
        "error" in result or str(result.get("status", "")).lower() in {"failed", "failure"}
    ):
        outcome.update(failed=True, level=logging.WARNING)
    if outcome["failed"]:
        trace.get_current_span().set_attribute("operation.outcome", "unsuccessful")
        if outcome["level"] >= logging.ERROR:
            trace.get_current_span().set_status(StatusCode.ERROR)


@contextmanager
def _function_call(name, attributes, log_completion):
    # Join an existing request/job trace. Startup helpers and sampling decisions
    # must not produce independent root spans for every tiny function call.
    enabled = (
        settings.OTEL_ENABLED and settings.OTEL_FUNCTION_TRACING_ENABLED
        and trace.get_current_span().is_recording()
    )
    log_success = log_completion and settings.LOG_OPERATION_COMPLETIONS
    start = time.perf_counter() if log_success else None
    span = tracer.start_span(name, attributes=attributes) if enabled else None
    outcome = {"failed": False, "logged": False, "level": logging.INFO}
    token = _function_outcome.set(outcome)
    try:
        with trace.use_span(
            span or trace.get_current_span(), end_on_exit=enabled,
            record_exception=False, set_status_on_exception=False,
        ):
            try:
                yield
            except (StopIteration, GeneratorExit):
                raise
            except asyncio.CancelledError:
                if span is not None:
                    span.set_attribute("operation.cancelled", True)
                if log_completion:
                    logger.info("Operation cancelled", extra={"operation": name, "outcome": "cancelled"})
                raise
            except Exception as error:
                if span is not None:
                    span.set_attribute("error.type", type(error).__name__)
                    span.set_status(StatusCode.ERROR)
                if log_completion:
                    status_code = getattr(error, "status_code", None)
                    level = logging.WARNING if isinstance(status_code, int) and status_code < 500 else logging.ERROR
                    log_failure(name, error, level=level)
                raise
            else:
                if log_completion and not outcome["logged"] and (log_success or outcome["failed"]):
                    logger.log(outcome["level"],
                               "Operation completed with unsuccessful outcome" if outcome["failed"] else "Operation completed",
                               extra={
                                   "operation": name,
                                   "outcome": "unsuccessful" if outcome["failed"] else "success",
                                   **({"duration_ms": round((time.perf_counter() - start) * 1000, 2)}
                                      if start is not None else {}),
                               })
    finally:
        _function_outcome.reset(token)


class _TracedIterator:
    """Attach span context only while a generator executes, never across yield."""

    def __init__(self, iterator, name, attributes):
        self.iterator = iterator
        self.name = name
        self.attributes = attributes

    def __iter__(self):
        return self

    def __next__(self):
        with _function_call(self.name, self.attributes, False):
            return next(self.iterator)

    def send(self, value):
        with _function_call(self.name, self.attributes, False):
            return self.iterator.send(value)

    def throw(self, *args):
        with _function_call(self.name, self.attributes, False):
            return self.iterator.throw(*args)

    def close(self):
        with _function_call(self.name, self.attributes, False):
            return self.iterator.close()


def trace_function(function=None, *, log_completion=False):
    """Trace sync/async functions and generator execution without capturing values."""
    if function is None:
        return partial(trace_function, log_completion=log_completion)
    if getattr(function, "__jntuh_traced__", False):
        return function
    # Decide once at import time. In boundary mode tiny helpers, validators,
    # per-row projections and generator steps incur no wrapper cost at all.
    boundary = log_completion or (
        function.__module__ in {
            "api.routes", "database.operations", "database.jobOperations", "utils.s3",
        } and not function.__name__.startswith("_")
    ) or (
        function.__module__ in {"chatbot.provider", "chatbot.tools"}
        and function.__name__ in {"complete", "execute"}
    )
    tracing_enabled = settings.OTEL_ENABLED and settings.OTEL_FUNCTION_TRACING_ENABLED
    detailed = settings.OTEL_FUNCTION_TRACING_MODE == "full"
    if not log_completion and (not tracing_enabled or (not detailed and not boundary)):
        return function
    name = f"{function.__module__}.{function.__qualname__}".replace(".<locals>.", ".")
    attributes = _function_attributes(function)

    if inspect.iscoroutinefunction(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            if not log_completion and not trace.get_current_span().is_recording():
                return await function(*args, **kwargs)
            with _function_call(name, attributes, log_completion):
                result = await function(*args, **kwargs)
                if log_completion:
                    _record_function_result(result)
                return result
    elif inspect.isgeneratorfunction(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not trace.get_current_span().is_recording():
                return (yield from function(*args, **kwargs))
            return (yield from _TracedIterator(function(*args, **kwargs), name, attributes))
    else:
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not log_completion and not trace.get_current_span().is_recording():
                return function(*args, **kwargs)
            with _function_call(name, attributes, log_completion):
                result = function(*args, **kwargs)
                if log_completion:
                    _record_function_result(result)
                return result

    wrapped.__jntuh_traced__ = True
    return wrapped


def trace_headers():
    headers = {}
    propagator.inject(headers)
    return headers


def consume_operation(queue_name, headers):
    return operation(
        "rabbitmq.process", kind=SpanKind.CONSUMER,
        context=propagator.extract(headers or {}),
        attributes={"messaging.system": "rabbitmq", "messaging.destination.name": queue_name},
    )


class RequestTelemetryMiddleware:
    """ASGI wrapper includes guard rejections, errors, and streaming duration."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/metrics":
            return await self.app(scope, receive, send)
        method = scope["method"]
        request_id = uuid4().hex
        carrier = {key.decode("latin1"): value.decode("latin1") for key, value in scope["headers"]}
        start = time.perf_counter()
        status_code = 500
        with tracer.start_as_current_span(
            method,
            context=propagator.extract(carrier) if "traceparent" in carrier else None,
            kind=SpanKind.SERVER,
            attributes={"http.request.method": method, "request.id": request_id},
            record_exception=False, set_status_on_exception=False,
        ) as span:
            async def send_response(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", request_id.encode()))
                    context = span.get_span_context()
                    if context.is_valid:
                        headers.append((b"x-trace-id", format(context.trace_id, "032x").encode()))
                    message = {**message, "headers": headers}
                await send(message)
            try:
                await self.app(scope, receive, send_response)
            except Exception as error:
                span.set_attribute("error.type", type(error).__name__)
                span.set_status(StatusCode.ERROR)
                raise
            finally:
                route = getattr(scope.get("route"), "path", "unmatched")
                span.update_name(f"{method} {route}")
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", status_code)
                if status_code >= 500:
                    span.set_status(StatusCode.ERROR)
                level = (logging.ERROR if status_code >= 500 else
                         logging.WARNING if status_code >= 400 else logging.INFO)
                logger.log(level,
                           "HTTP request completed", extra={
                               "request_id": request_id, "method": method, "route": route,
                               "status_code": status_code,
                               "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                           })
