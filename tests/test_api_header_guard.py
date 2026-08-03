import asyncio
import json
import os
import sys
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


for name, value in {
    "RABBITMQ_URL": "amqp://guest:guest@localhost/",
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/jntuh",
    "QUEUE_NAME": "test",
    "REDIS_URL": "redis://localhost:6379/0",
    "VAPID_PUBLIC_KEY": "test",
    "VAPID_PRIVATE_KEY": "test",
    "TELEGRAM_TOKEN": "test",
    "TELEGRAM_CHAT_ID": "test",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_REGION": "us-east-1",
    "S3_BUCKET_NAME": "test",
    "GRACE_MARKS_ADMIN_KEY": "test",
}.items():
    os.environ.setdefault(name, value)


from config import apiHeaderGuard  # noqa: E402


def _request(user_agent: str, api_key: str | None = None) -> Request:
    headers = [(b"user-agent", user_agent.encode())]
    if api_key is not None:
        headers.append((b"x-api-key", api_key.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/api/results",
            "raw_path": b"/api/results",
            "query_string": b"",
            "headers": headers,
            "server": ("testserver", 443),
            "client": ("127.0.0.1", 1234),
        }
    )


async def _dispatch(user_agent: str, api_key: str | None = None) -> Response:
    middleware = object.__new__(apiHeaderGuard.ApiKeyHeaderMiddleware)

    async def call_next(_request: Request) -> Response:
        return Response(status_code=204)

    return await middleware.dispatch(_request(user_agent, api_key), call_next)


def test_ios_user_agent_bypasses_api_key(monkeypatch):
    monkeypatch.setattr(apiHeaderGuard, "API_ACCESS_KEY", "secret")

    response = asyncio.run(_dispatch("JNTUH-Connect-iOS/1.0"))

    assert response.status_code == 204


def test_similar_ios_user_agent_does_not_bypass_api_key(monkeypatch):
    monkeypatch.setattr(apiHeaderGuard, "API_ACCESS_KEY", "secret")

    response = asyncio.run(_dispatch("JNTUH-Connect-iOS/1.0-spoof"))

    assert response.status_code == 403
    assert json.loads(response.body) == {"detail": "Authentication failed"}


def test_other_user_agent_still_requires_valid_api_key(monkeypatch):
    monkeypatch.setattr(apiHeaderGuard, "API_ACCESS_KEY", "secret")

    missing = asyncio.run(_dispatch("Mozilla/5.0"))
    wrong = asyncio.run(_dispatch("Mozilla/5.0", "wrong"))
    valid = asyncio.run(_dispatch("Mozilla/5.0", "secret"))

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert valid.status_code == 204
