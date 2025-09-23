import os
import sys
from dotenv import load_dotenv

from utils.logger import logger

load_dotenv()

required_env_vars = [
    "RABBITMQ_URL",
    "DATABASE_URL",
    "QUEUE_NAME",
    "REDIS_URL",
    "VAPID_PUBLIC_KEY",
    "VAPID_PRIVATE_KEY",
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
DB_URL = os.getenv("DATABASE_URL")
QUEUE_NAME = os.getenv("QUEUE_NAME")
REDIS_URL = os.getenv("REDIS_URL")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

NOTIFICATIONS_EXPIRY_TIME = 1800
EXPIRY_TIME = 1200
FIVE_MINUTE_EXPIRY = 300
NOTIFICATIONS_REDIS_KEY = "notificationsi"
REDIS_URL_KEY = "url"
SEMESTERS = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]
RABBITMQ_MAX_MESSAGES = 4000
RABBITMQ_CLASS_MAX_MESSAGES = 10
RABBITMQ_ROLL_NUMBERS = "rabbitmq_roll_numbers"

logger.info("All required environment variables are set. Starting application...")
