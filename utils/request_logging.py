"""Structured, privacy-aware HTTP access logging helpers."""

from __future__ import annotations

import ipaddress
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Mapping

from starlette.requests import Request

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_MAX_HEADER_LENGTH = 1024


def _safe_header(value: str | None, max_length: int = _MAX_HEADER_LENGTH) -> str | None:
    """Bound untrusted header values and remove control characters."""
    if not value:
        return None
    cleaned = "".join(char for char in value if char >= " " and char != "\x7f")
    return cleaned[:max_length] or None


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def resolve_client_ip(
    headers: Mapping[str, str], socket_peer_ip: str | None
) -> tuple[str, str]:
    """Resolve client IP using the same proxy-header order as production."""
    cf_ip = _valid_ip(headers.get("cf-connecting-ip"))
    if cf_ip:
        return cf_ip, "cf-connecting-ip"

    forwarded_for = headers.get("x-forwarded-for", "")
    for candidate in forwarded_for.split(","):
        forwarded_ip = _valid_ip(candidate)
        if forwarded_ip:
            return forwarded_ip, "x-forwarded-for"

    peer_ip = _valid_ip(socket_peer_ip)
    return (peer_ip or "unknown"), "socket"


def parse_user_agent(user_agent: str | None) -> dict[str, str]:
    """Return useful device fields without introducing a UA-parser dependency."""
    ua = user_agent or ""
    lower = ua.lower()

    browser_patterns = (
        ("Edge", r"(?:Edg|EdgiOS|EdgA)/([\w.]+)"),
        ("Opera", r"(?:OPR|Opera)/([\w.]+)"),
        ("Chrome", r"(?:Chrome|CriOS)/([\w.]+)"),
        ("Firefox", r"(?:Firefox|FxiOS)/([\w.]+)"),
        ("Safari", r"Version/([\w.]+).+Safari/"),
        ("OkHttp", r"okhttp/([\w.]+)"),
        ("Dalvik", r"Dalvik/([\w.]+)"),
        ("curl", r"curl/([\w.]+)"),
        ("HTTPX", r"python-httpx/([\w.]+)"),
        ("Python Requests", r"python-requests/([\w.]+)"),
    )
    browser = "Other"
    browser_version = None
    for name, pattern in browser_patterns:
        match = re.search(pattern, ua, re.IGNORECASE)
        if match:
            browser = name
            browser_version = match.group(1)
            break

    if "android" in lower:
        operating_system = "Android"
        os_match = re.search(r"Android\s+([^;)\s]+)", ua, re.IGNORECASE)
    elif any(token in lower for token in ("iphone", "ipad", "ios")):
        operating_system = "iOS"
        os_match = re.search(r"(?:CPU (?:iPhone )?OS|iPhone OS)\s+([\d_]+)", ua)
    elif "windows" in lower:
        operating_system = "Windows"
        os_match = re.search(r"Windows NT\s+([\d.]+)", ua, re.IGNORECASE)
    elif "mac os x" in lower or "macintosh" in lower:
        operating_system = "macOS"
        os_match = re.search(r"Mac OS X\s+([\d_]+)", ua, re.IGNORECASE)
    elif "cros" in lower:
        operating_system = "ChromeOS"
        os_match = re.search(r"CrOS\s+\S+\s+([\d.]+)", ua, re.IGNORECASE)
    elif "linux" in lower:
        operating_system = "Linux"
        os_match = None
    else:
        operating_system = "Other"
        os_match = None

    os_version = os_match.group(1).replace("_", ".") if os_match else None

    device_model = None
    android_model = re.search(
        r"Android\s+[^;)\s]+;\s*(?:[a-z]{2}-[a-z]{2};\s*)?([^;)]+)",
        ua,
        re.IGNORECASE,
    )
    if android_model:
        device_model = re.split(r"\s+Build/", android_model.group(1), 1)[0].strip()
    elif "ipad" in lower:
        device_model = "iPad"
    elif "iphone" in lower:
        device_model = "iPhone"

    if any(token in lower for token in ("bot", "crawler", "spider", "slurp")):
        device_type = "bot"
    elif "ipad" in lower or "tablet" in lower:
        device_type = "tablet"
    elif any(token in lower for token in ("mobile", "iphone", "android", "dalvik")):
        device_type = "mobile"
    elif any(
        token in lower
        for token in ("windows", "macintosh", "x11", "cros", "linux")
    ):
        device_type = "desktop"
    elif browser in {"OkHttp", "curl", "HTTPX", "Python Requests"}:
        device_type = "library"
    else:
        device_type = "unknown"

    return {
        "device_type": device_type,
        "device_model": device_model or "unknown",
        "browser": browser,
        "browser_version": browser_version or "unknown",
        "os": operating_system,
        "os_version": os_version or "unknown",
    }


def get_request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id")
    if supplied and _REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return str(uuid.uuid4())


def build_access_log(
    request: Request,
    *,
    request_id: str,
    started_at: float,
    status_code: int,
    response_content_length: str | None = None,
    exception_type: str | None = None,
) -> dict[str, object]:
    """Build a JSON-serializable access event without credentials or bodies."""
    socket_peer_ip = request.client.host if request.client else None
    client_ip, ip_source = resolve_client_ip(request.headers, socket_peer_ip)
    user_agent = _safe_header(request.headers.get("user-agent"), 512)
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)

    forwarded_for = []
    for value in request.headers.get("x-forwarded-for", "").split(","):
        valid_ip = _valid_ip(value)
        if valid_ip:
            forwarded_for.append(valid_ip)

    event: dict[str, object] = {
        "event": "http_request",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "route": route_path,
        # Values can contain credentials/PII, so only parameter names are logged.
        "query_parameter_names": sorted(set(request.query_params.keys())),
        "status_code": status_code,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "client_ip": client_ip,
        "client_ip_source": ip_source,
        "socket_peer_ip": _valid_ip(socket_peer_ip),
        "forwarded_for": forwarded_for,
        "origin": _safe_header(request.headers.get("origin")),
        "referer": _safe_header(request.headers.get("referer")),
        "host": _safe_header(request.headers.get("host"), 255),
        "scheme": request.url.scheme,
        "http_version": request.scope.get("http_version"),
        "user_agent": user_agent,
        **parse_user_agent(user_agent),
        "accept_language": _safe_header(request.headers.get("accept-language"), 255),
        "content_type": _safe_header(request.headers.get("content-type"), 255),
        "request_content_length": _safe_header(
            request.headers.get("content-length"), 32
        ),
        "response_content_length": _safe_header(response_content_length, 32),
        "api_key_present": bool(request.headers.get("x-api-key")),
        "cloudflare_ray": _safe_header(request.headers.get("cf-ray"), 128),
        "cloudflare_country": _safe_header(request.headers.get("cf-ipcountry"), 8),
    }
    if exception_type:
        event["exception_type"] = exception_type
    return event


def serialize_access_log(event: Mapping[str, object]) -> str:
    return json.dumps(event, separators=(",", ":"), sort_keys=True, default=str)
