import logging

# Common log format
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Main Logger
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.FileHandler("app.log"),  # General app logs
        logging.StreamHandler(),  # Print to console
    ],
)

# Separate loggers for RabbitMQ & Database
rabbitmq_logger = logging.getLogger("rabbitmq")
database_logger = logging.getLogger("database")
redis_logger = logging.getLogger("redis")

# Add separate handlers for RabbitMQ logs
rabbitmq_handler = logging.FileHandler("rabbitmq.log")
rabbitmq_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
rabbitmq_logger.addHandler(rabbitmq_handler)

# Add separate handlers for Database logs
database_handler = logging.FileHandler("database.log")
database_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
database_logger.addHandler(database_handler)

# Add separate handlers for Redis logs
redis_handler = logging.FileHandler("redis.log")
redis_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
redis_logger.addHandler(redis_handler)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
