"""Prometheus counter for HTTP traffic split by client platform (see
utils.platform.detect_platform). Lets Grafana chart/alert on Android vs iOS
vs web vs other traffic and error rates independently."""

from prometheus_client import Counter

HTTP_REQUESTS_BY_PLATFORM = Counter(
    "http_requests_by_platform_total",
    "Total HTTP requests, labeled by client platform and response status.",
    labelnames=("platform", "status"),
)
