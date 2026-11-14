"""Optional telemetry settings; no new startup-required configuration."""

import os

from dotenv import load_dotenv

load_dotenv()

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "jntuh-backend")
OTEL_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
OTEL_TRACES_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
OTEL_FUNCTION_TRACING_ENABLED = (
    os.getenv("OTEL_FUNCTION_TRACING_ENABLED", "true").lower() == "true"
)
OTEL_FUNCTION_TRACING_MODE = os.getenv("OTEL_FUNCTION_TRACING_MODE", "boundary").lower()
OTEL_TRACE_SAMPLE_RATIO = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "0.1"))
OTEL_SPAN_QUEUE_SIZE = int(os.getenv("OTEL_BSP_MAX_QUEUE_SIZE", "16384"))
OTEL_SPAN_BATCH_SIZE = int(os.getenv("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", "1024"))
OTEL_SPAN_SCHEDULE_DELAY = int(os.getenv("OTEL_BSP_SCHEDULE_DELAY", "1000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIRECTORY = os.getenv("LOG_DIRECTORY", ".")
LOG_FILE_ENABLED = os.getenv("LOG_FILE_ENABLED", "false").lower() == "true"
LOG_OPERATION_COMPLETIONS = os.getenv("LOG_OPERATION_COMPLETIONS", "false").lower() == "true"
LOG_QUEUE_SIZE = int(os.getenv("LOG_QUEUE_SIZE", "4096"))
WORKER_METRICS_ENABLED = os.getenv("WORKER_METRICS_ENABLED", "false").lower() == "true"
WORKER_METRICS_HOST = os.getenv("WORKER_METRICS_HOST", "0.0.0.0")
WORKER_METRICS_PORT = int(os.getenv("WORKER_METRICS_PORT", "8001"))
