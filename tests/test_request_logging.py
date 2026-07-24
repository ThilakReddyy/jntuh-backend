import json
import time

from starlette.requests import Request

from utils.request_logging import (
    build_access_log,
    get_request_id,
    parse_user_agent,
    resolve_client_ip,
    serialize_access_log,
)


def _request(headers=None, path="/results/22ABC12345?token=secret"):
    raw_headers = [
        (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path.split("?", 1)[0],
            "query_string": path.partition("?")[2].encode(),
            "headers": raw_headers,
            "client": ("10.0.0.2", 1234),
            "server": ("api.example.com", 443),
            "scheme": "https",
            "http_version": "1.1",
        }
    )


def test_client_ip_prefers_cloudflare_then_forwarded_then_socket():
    assert resolve_client_ip(
        {"cf-connecting-ip": "203.0.113.8", "x-forwarded-for": "198.51.100.2"},
        "10.0.0.2",
    ) == ("203.0.113.8", "cf-connecting-ip")
    assert resolve_client_ip(
        {"x-forwarded-for": "198.51.100.2, 10.0.0.1"}, "10.0.0.2"
    ) == ("198.51.100.2", "x-forwarded-for")
    assert resolve_client_ip({"x-forwarded-for": "not-an-ip"}, "10.0.0.2") == (
        "10.0.0.2",
        "socket",
    )


def test_user_agent_parses_android_device():
    parsed = parse_user_agent(
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "Chrome/126.0 Mobile Safari/537.36"
    )
    assert parsed == {
        "device_type": "mobile",
        "device_model": "Pixel 8",
        "browser": "Chrome",
        "browser_version": "126.0",
        "os": "Android",
        "os_version": "14",
    }


def test_access_log_is_structured_and_does_not_log_secrets():
    request = _request(
        {
            "CF-Connecting-IP": "203.0.113.8",
            "Origin": "https://jntuhconnect.dhethi.com",
            "User-Agent": "okhttp/4.12.0",
            "X-Api-Key": "do-not-log-me",
            "Authorization": "Bearer do-not-log-me",
            "X-Request-ID": "frontend-123",
        }
    )

    event = build_access_log(
        request,
        request_id=get_request_id(request),
        started_at=time.perf_counter(),
        status_code=200,
    )
    serialized = serialize_access_log(event)
    decoded = json.loads(serialized)

    assert decoded["request_id"] == "frontend-123"
    assert decoded["client_ip"] == "203.0.113.8"
    assert decoded["origin"] == "https://jntuhconnect.dhethi.com"
    assert decoded["browser"] == "OkHttp"
    assert decoded["query_parameter_names"] == ["token"]
    assert decoded["api_key_present"] is True
    assert "secret" not in serialized
    assert "do-not-log-me" not in serialized


def test_invalid_request_id_is_replaced():
    request = _request({"X-Request-ID": "bad request id\ninjection"})
    assert get_request_id(request) != "bad request id\ninjection"
