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
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "S3_BUCKET_NAME",
    "GRACE_MARKS_ADMIN_KEY",
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
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") or None
S3_PUBLIC_URL_BASE = os.getenv("S3_PUBLIC_URL_BASE") or None
GRACE_MARKS_ADMIN_KEY = os.getenv("GRACE_MARKS_ADMIN_KEY")
GRACE_MARKS_PROOF_MAX_BYTES = 5 * 1024 * 1024
GRACE_MARKS_PROOF_ALLOWED_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
}

NOTIFICATIONS_EXPIRY_TIME = 1800
EXPIRY_TIME = 1200
FIVE_MINUTE_EXPIRY = 300
NOTIFICATIONS_REDIS_KEY = "notificationsi"
LATEST_NOTIFICATIONS_REDIS_KEY = "latest_notifications"
REDIS_URL_KEY = "url"
SEMESTERS = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]
RABBITMQ_MAX_MESSAGES = 4000
RABBITMQ_CLASS_MAX_MESSAGES = 200
RABBITMQ_ROLL_NUMBERS = "rabbitmq_roll_numbers"
RESULTS = "results"
ALL = "all"
EXAMS = "exams"

logger.info("All required environment variables are set. Starting application...")
