"""Bounded metrics and OpenTelemetry spans shared by the API and worker.

Identifiers, query strings, credentials and payloads never become metric labels
or span attributes. Logs carry request/trace IDs for investigation in Grafana.
"""
import contextvars
import functools
import logging
import os
import re
import time
import uuid
from contextlib import contextmanager

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

_operation_state = contextvars.ContextVar("operation_state", default=None)
request_id_context = contextvars.ContextVar("request_id", default="")
tracer = trace.get_tracer("jntuh")
_provider = None
HTTP_REQUESTS = Counter("jntuh_http_requests_total", "HTTP responses", ["method", "route", "status"])
HTTP_DURATION = Histogram("jntuh_http_request_duration_seconds", "HTTP latency", ["method", "route"], buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10, 30, 60))
HTTP_ACTIVE = Gauge("jntuh_http_requests_in_progress", "Active HTTP requests")
OPERATIONS = Counter("jntuh_operations_total", "Application operation outcomes", ["component", "operation", "outcome"])
OP_DURATION = Histogram("jntuh_operation_duration_seconds", "Application operation latency", ["component", "operation"], buckets=(.005, .025, .1, .5, 1, 5, 15, 60, 300, 900))
OP_ACTIVE = Gauge("jntuh_operations_in_progress", "Active application operations", ["component", "operation"])
CACHE = Counter("jntuh_cache_reads_total", "Result cache reads", ["outcome"])
WORKER_CONNECTED = Gauge("jntuh_worker_connected", "Worker has connected to dependencies and declared queues")
WORKER_HEARTBEAT = Gauge("jntuh_worker_heartbeat_timestamp_seconds", "Last worker event loop heartbeat")
EXCLUDED_PATHS = {"/metrics", "/health/live", "/health/ready", "/api/health"}


def setup_telemetry(service_name):
    global _provider
    if _provider is not None or not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    _provider = TracerProvider(
        resource=Resource.create({
            "service.name": service_name,
            "service.version": os.getenv("APP_VERSION", "development"),
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        }),
        sampler=ParentBased(TraceIdRatioBased(float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1")))),
    )
    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(_provider)


def shutdown_telemetry():
    if _provider is not None:
        _provider.shutdown()


@contextmanager
def operation(component, name, *, kind=SpanKind.INTERNAL, context=None):
    """Record success/error even when a caller converts an exception to a response.

    A caller can set outcome to empty, unavailable, rejected, or error when no
    exception escapes. Metric label values must be fixed developer literals.
    """
    start = time.perf_counter()
    state = {"outcome": "success"}
    token = _operation_state.set(state)
    OP_ACTIVE.labels(component, name).inc()
    with tracer.start_as_current_span(f"{component}.{name}", kind=kind, context=context,
                                      record_exception=False, set_status_on_exception=False) as span:
        try:
            yield state
        except BaseException:
            state["outcome"] = "error"
            raise
        finally:
            outcome = state["outcome"]
            span.set_attribute("operation.outcome", outcome)
            if outcome in {"error", "unavailable"}:
                span.set_status(Status(StatusCode.ERROR))
            OPERATIONS.labels(component, name, outcome).inc()
            OP_DURATION.labels(component, name).observe(time.perf_counter() - start)
            OP_ACTIVE.labels(component, name).dec()
            _operation_state.reset(token)
            logging.getLogger("operations").log(
                logging.ERROR if outcome == "error" else logging.INFO,
                "operation completed", extra={"component": component, "operation": name, "outcome": outcome},
            )


def set_operation_outcome(outcome):
    """Mark failures handled by legacy functions that return instead of raising."""
    state = _operation_state.get()
    if state is not None:
        state["outcome"] = outcome


def observed(component, name, *, empty_result=False):
    def decorate(fn):
        @functools.wraps(fn)
        async def wrapped(*args, **kwargs):
            with operation(component, name) as state:
                result = await fn(*args, **kwargs)
                if empty_result and state["outcome"] == "success" and (result is None or result is False):
                    state["outcome"] = "empty"
                return result
        return wrapped
    return decorate


class RequestTelemetryMiddleware:
    """Pure ASGI middleware, including early auth failures and unhandled errors."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in EXCLUDED_PATHS:
            return await self.app(scope, receive, send)
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope["headers"]}
        request_id = headers.get("x-request-id", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", request_id):
            request_id = uuid.uuid4().hex
        token = request_id_context.set(request_id)
        method = scope.get("method", "OTHER")
        if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}:
            method = "OTHER"
        start = time.perf_counter()
        status = 500
        HTTP_ACTIVE.inc()
        try:
            with tracer.start_as_current_span("HTTP request", context=propagate.extract(headers),
                                              kind=SpanKind.SERVER, record_exception=False,
                                              set_status_on_exception=False) as span:
                async def send_response(message):
                    nonlocal status
                    if message["type"] == "http.response.start":
                        status = message["status"]
                        response_headers = list(message.get("headers", []))
                        response_headers.append((b"x-request-id", request_id.encode()))
                        if span.get_span_context().is_valid:
                            response_headers.append((b"x-trace-id", format(span.get_span_context().trace_id, "032x").encode()))
                        message = {**message, "headers": response_headers}
                    await send(message)
                try:
                    await self.app(scope, receive, send_response)
                finally:
                    route_obj = scope.get("route")
                    route = getattr(route_obj, "path", None) or ("/mcp" if scope["path"].startswith("/mcp") else "unmatched")
                    elapsed = time.perf_counter() - start
                    span.update_name(f"{method} {route}")
                    span.set_attributes({"http.request.method": method, "http.route": route,
                                         "http.response.status_code": status, "request.id": request_id})
                    if status >= 500:
                        span.set_status(Status(StatusCode.ERROR))
                    exemplar = {"trace_id": format(span.get_span_context().trace_id, "032x")} if span.is_recording() else None
                    HTTP_REQUESTS.labels(method, route, str(status)).inc(exemplar=exemplar)
                    HTTP_DURATION.labels(method, route).observe(elapsed, exemplar=exemplar)
                    logging.getLogger("http").log(logging.ERROR if status >= 500 else logging.INFO,
                        "request completed", extra={"method": method, "route": route, "status": status,
                                                    "duration_ms": round(elapsed * 1000, 2)})
        finally:
            HTTP_ACTIVE.dec()
            request_id_context.reset(token)


class MetricsEndpoint:
    """Callable object keeps Starlette from treating the ASGI function as a route handler."""
    def __init__(self):
        self.app = make_asgi_app()

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)
