import math
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
# Optional shared secret for the X-Api-Key header guard. When set, the header
# value must match exactly; when unset, any non-empty value passes.
API_ACCESS_KEY = os.getenv("API_ACCESS_KEY") or None
# Optional OpenAI-compatible chatbot provider. These are deliberately not in
# required_env_vars so existing deployments continue to start without them.
CHATBOT_API_KEY = os.getenv("CHATBOT_API_KEY") or None
CHATBOT_BASE_URL = os.getenv("CHATBOT_BASE_URL") or None
CHATBOT_MODEL = os.getenv("CHATBOT_MODEL") or None


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return min(max(int(os.getenv(name, str(default))), minimum), maximum)
    except ValueError:
        logger.warning(f"Invalid {name}; using default value {default}")
        return default


def _bounded_float_env(
    name: str, default: float, minimum: float, maximum: float
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        if not math.isfinite(value):
            raise ValueError
        return min(max(value, minimum), maximum)
    except ValueError:
        logger.warning(f"Invalid {name}; using default value {default}")
        return default


CHATBOT_TIMEOUT_SECONDS = _bounded_float_env(
    "CHATBOT_TIMEOUT_SECONDS", 30.0, 1.0, 120.0
)
CHATBOT_MAX_ITERATIONS = _bounded_int_env("CHATBOT_MAX_ITERATIONS", 4, 2, 6)
CHATBOT_MAX_TOOL_CALLS = _bounded_int_env("CHATBOT_MAX_TOOL_CALLS", 6, 1, 10)
CHATBOT_MAX_OUTPUT_TOKENS = _bounded_int_env(
    "CHATBOT_MAX_OUTPUT_TOKENS", 800, 100, 2000
)
# Set ENVIRONMENT=production to disable the interactive docs (/docs, /redoc,
# /openapi.json). Anything else (or unset) keeps them enabled.
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"
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
# Calendars / syllabus change rarely — cache the built trees for a day.
CONTENT_EXPIRY_TIME = 86400
NOTIFICATIONS_REDIS_KEY = "notificationsi"
LATEST_NOTIFICATIONS_REDIS_KEY = "latest_notifications"
CALENDARS_REDIS_KEY = "academic_calendars_tree"
SYLLABUS_REDIS_KEY = "syllabus_tree"
REDIS_URL_KEY = "url"
SEMESTERS = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]
RABBITMQ_MAX_MESSAGES = 4000
RABBITMQ_CLASS_MAX_MESSAGES = 200
RABBITMQ_ROLL_NUMBERS = "rabbitmq_roll_numbers"
RESULTS = "results"
ALL = "all"
EXAMS = "exams"

logger.info("All required environment variables are set. Starting application...")
