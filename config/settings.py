import os
import sys
from dotenv import load_dotenv

from utils.logger import logger

load_dotenv()

required_env_vars = ["RABBITMQ_URL", "DATABASE_URL", "QUEUE_NAME", "REDIS_URL"]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
DB_URL = os.getenv("DATABASE_URL")
QUEUE_NAME = os.getenv("QUEUE_NAME")
REDIS_URL = os.getenv("REDIS_URL")

EXPIRY_TIME = 3600
FIVE_MINUTE_EXPIRY = 300
NOTIFICATIONS_REDIS_KEY = "notificationsi"
REDIS_URL_KEY = "url"
SEMESTERS = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]

logger.info("All required environment variables are set. Starting application...")
