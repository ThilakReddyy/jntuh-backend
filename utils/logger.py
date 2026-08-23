import json
import logging
import logging.handlers
import os
import queue
from logging_loki import LokiQueueHandler

from utils.requestContext import get_platform, get_request_id
from utils.scrub import scrub_text

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOKI_ENDPOINT = os.getenv("LOKI_ENDPOINT", "http://loki:3100/loki/api/v1/push")

LOG_MAX_BYTES = 20 * 1024 * 1024  # 20 MB
LOG_BACKUP_COUNT = 5

log_queue = queue.Queue(-1)  # -1 for infinite size
loki_handler = LokiQueueHandler(
    queue=log_queue,
    url=LOKI_ENDPOINT,
    tags={"application": "fastapi"},
    version="1",
)


class RequestIdFilter(logging.Filter):
    """Injects the current request's correlation ID and client platform
    (android/ios/web/other, see utils.platform) into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.platform = get_platform()
        return True


class JsonFormatter(logging.Formatter):
    """Structured JSON logs, scrubbed of student-data-shaped tokens, so
    Loki/Grafana can filter/build panels on request_id/level/logger."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_text(record.getMessage()),
            "request_id": getattr(record, "request_id", "-"),
            "platform": getattr(record, "platform", "-"),
        }
        if record.exc_info:
            payload["exception"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload)


def _rotating_handler(filename: str) -> logging.handlers.RotatingFileHandler:
    handler = logging.handlers.RotatingFileHandler(
        filename, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    return handler


# Main Logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        _rotating_handler("app.log"),  # General app logs
        logging.StreamHandler(),  # Print to console
        loki_handler,
    ],
)
for _handler in logging.getLogger().handlers:
    if _handler.formatter is None:
        _handler.setFormatter(JsonFormatter())
    if not any(isinstance(f, RequestIdFilter) for f in _handler.filters):
        _handler.addFilter(RequestIdFilter())

# Separate loggers for RabbitMQ & Database
rabbitmq_logger = logging.getLogger("rabbitmq")
database_logger = logging.getLogger("database")
redis_logger = logging.getLogger("redis")
scraping_logger = logging.getLogger("scraping")
telegram_logger = logging.getLogger("telegram")


def add_file_handler(logger, filename):
    logger.addHandler(_rotating_handler(filename))
    logger.addHandler(loki_handler)  # Send component logs to Loki as well


add_file_handler(rabbitmq_logger, "rabbitmq.log")
add_file_handler(database_logger, "database.log")
add_file_handler(redis_logger, "redis.log")
add_file_handler(scraping_logger, "scraper.log")
add_file_handler(telegram_logger, "telegram.log")

logging.getLogger("httpx").setLevel(logging.ERROR)


logger = logging.getLogger(__name__)
