"""Structured stdout logs, collected once by Alloy from Docker.

No network calls or unbounded queues in application logging. Student roll
numbers in legacy messages are redacted; trace IDs provide correlation.
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

from opentelemetry import trace
from utils.observability import request_id_context

_ROLL = re.compile(r"\b\d{2}[A-Z0-9]{8}(?=[A-Z][a-z]|\b)", re.IGNORECASE)
_URL_SECRET = re.compile(r"(://)[^\s/@]+:[^\s/@]+@")
_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s]+")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        context = trace.get_current_span().get_span_context()
        message = _ROLL.sub("[roll-redacted]", record.getMessage())
        message = _URL_SECRET.sub(r"\1[redacted]@", message)
        message = _QUERY.sub(r"\1?[redacted]", message)
        data = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname,
                "service": os.getenv("OTEL_SERVICE_NAME", "jntuh-api"), "logger": record.name,
                "message": message, "request_id": request_id_context.get(),
                "trace_id": format(context.trace_id, "032x") if context.is_valid else "",
                "span_id": format(context.span_id, "016x") if context.is_valid else ""}
        for key in ("method", "route", "status", "duration_ms", "component", "operation", "outcome"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            # Exception messages may contain SQL parameters or provider credentials.
            data["exception_type"] = record.exc_info[0].__name__
        return json.dumps(data)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler], force=True)
for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(name).handlers.clear()
    logging.getLogger(name).propagate = True
# HTTP telemetry middleware already logs requests without raw query strings.
logging.getLogger("uvicorn.access").disabled = True
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("app")
rabbitmq_logger = logging.getLogger("rabbitmq")
database_logger = logging.getLogger("database")
redis_logger = logging.getLogger("redis")
scraping_logger = logging.getLogger("scraping")
telegram_logger = logging.getLogger("telegram")
