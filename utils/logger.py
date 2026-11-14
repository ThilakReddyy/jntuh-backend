"""JSON logs collected from Docker stdout by Alloy, without in-process I/O to Loki."""

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from opentelemetry import trace

from config.observability import LOG_DIRECTORY, LOG_LEVEL, OTEL_SERVICE_NAME


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
        if context.is_valid:
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


def _file_handler(name):
    # Separate files avoid API/worker races during rotation.
    directory = Path(LOG_DIRECTORY)
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        directory / f"{name}-{os.getpid()}.log", maxBytes=10 * 1024 * 1024,
        backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    return handler


root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)
if not getattr(root_logger, "_jntuh_configured", False):
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(_file_handler("app"))
    root_logger._jntuh_configured = True


def _component_logger(name, filename):
    component = logging.getLogger(name)
    if not component.handlers:
        component.addHandler(_file_handler(filename))
    # One propagation to stdout; Alloy delivers each record to Loki once.
    return component


rabbitmq_logger = _component_logger("rabbitmq", "rabbitmq")
database_logger = _component_logger("database", "database")
redis_logger = _component_logger("redis", "redis")
scraping_logger = _component_logger("scraping", "scraper")
telegram_logger = _component_logger("telegram", "telegram")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
