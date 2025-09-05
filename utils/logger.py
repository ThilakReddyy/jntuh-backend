import logging

import queue
from logging_loki import LokiQueueHandler


# Common log format
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s"
LOG_FORMAT = "%(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOKI_ENDPOINT = "http://loki:3100/loki/api/v1/push"

log_queue = queue.Queue(-1)  # -1 for infinite size
loki_handler = LokiQueueHandler(
    queue=log_queue,
    url=LOKI_ENDPOINT,
    tags={"application": "fastapi"},
    version="1",
)


# Main Logger
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.FileHandler("app.log"),  # General app logs
        logging.StreamHandler(),  # Print to console
        loki_handler,
    ],
)

# Separate loggers for RabbitMQ & Database
rabbitmq_logger = logging.getLogger("rabbitmq")
database_logger = logging.getLogger("database")
redis_logger = logging.getLogger("redis")
scraping_logger = logging.getLogger("scraping")
telegram_logger = logging.getLogger("telegram")


def add_file_handler(logger, filename):
    handler = logging.FileHandler(filename)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(handler)
    logger.addHandler(loki_handler)  # Send component logs to Loki as well


add_file_handler(rabbitmq_logger, "rabbitmq.log")
add_file_handler(database_logger, "database.log")
add_file_handler(redis_logger, "redis.log")
add_file_handler(scraping_logger, "scraper.log")
add_file_handler(telegram_logger, "telegram.log")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.ERROR)


logger = logging.getLogger(__name__)
