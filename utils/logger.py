"""Bounded, asynchronous JSON logging collected from Docker stdout by Alloy."""

import atexit
import copy
import json
import logging
import os
import queue
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path

from opentelemetry import trace
from prometheus_client import Counter

from config.observability import (
    LOG_DIRECTORY, LOG_FILE_ENABLED, LOG_LEVEL, LOG_QUEUE_SIZE, OTEL_SERVICE_NAME,
)

LOG_RECORDS_DROPPED = Counter(
    "application_log_records_dropped_total",
    "Log records dropped when the bounded output queue is full.",
)


class ContextQueueHandler(QueueHandler):
    def prepare(self, record):
        # The listener runs in another thread. Snapshot correlation before the
        # request's span ends, and avoid modifying other handlers' LogRecords.
        prepared = copy.copy(record)
        prepared.msg = record.getMessage()
        prepared.args = None
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            prepared.trace_id = format(context.trace_id, "032x")
            prepared.span_id = format(context.span_id, "016x")
        return prepared

    def enqueue(self, record):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # Never stall the API or recursively emit logging errors under load.
            LOG_RECORDS_DROPPED.inc()


class DrainingQueueListener(QueueListener):
    def enqueue_sentinel(self):
        # Only shutdown may wait while the listener drains its bounded queue.
        self.queue.put(self._sentinel)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        context = trace.get_current_span().get_span_context()
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": OTEL_SERVICE_NAME,
            "process_id": record.process,
            "message": record.getMessage(),
        }
        if getattr(record, "trace_id", None):
            entry["trace_id"] = record.trace_id
            entry["span_id"] = record.span_id
        elif context.is_valid:
            entry["trace_id"] = format(context.trace_id, "032x")
            entry["span_id"] = format(context.span_id, "016x")
        for field in (
            "request_id", "method", "route", "status_code", "duration_ms",
            "operation", "error_type", "outcome", "reason", "platform",
            "attempt", "count", "queue", "message_count", "inserted_count",
        ):
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def _file_handler(name, component=None):
    # Separate files avoid API/worker races during rotation.
    directory = Path(LOG_DIRECTORY)
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        directory / f"{name}-{os.getpid()}.log", maxBytes=10 * 1024 * 1024,
        backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    if component is not None:
        handler.addFilter(logging.Filter(component))
    return handler


root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)
if not getattr(root_logger, "_jntuh_configured", False):
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())
    outputs = [stream_handler]
    if LOG_FILE_ENABLED:
        outputs.append(_file_handler("app"))
        for component, filename in (
            ("rabbitmq", "rabbitmq"), ("database", "database"),
            ("redis", "redis"), ("scraping", "scraper"), ("telegram", "telegram"),
        ):
            outputs.append(_file_handler(filename, component))
    log_queue = queue.Queue(maxsize=LOG_QUEUE_SIZE)
    listener = DrainingQueueListener(log_queue, *outputs, respect_handler_level=True)
    root_logger.addHandler(ContextQueueHandler(log_queue))
    listener.start()
    atexit.register(listener.stop)
    root_logger._jntuh_listener = listener
    root_logger._jntuh_configured = True


def _component_logger(name):
    # Component file outputs, if enabled, are routed in the listener thread.
    return logging.getLogger(name)


rabbitmq_logger = _component_logger("rabbitmq")
database_logger = _component_logger("database")
redis_logger = _component_logger("redis")
scraping_logger = _component_logger("scraping")
telegram_logger = _component_logger("telegram")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
