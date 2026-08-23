"""Per-request correlation ID, threaded through structured logs instead of a
full tracing backend (see CLAUDE.md Observability section)."""

from contextvars import ContextVar
from uuid import uuid4

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
_platform_ctx: ContextVar[str] = ContextVar("platform", default="-")


def set_request_id(request_id: str | None = None) -> str:
    value = request_id or uuid4().hex
    _request_id_ctx.set(value)
    return value


def get_request_id() -> str:
    return _request_id_ctx.get()


def set_platform(platform: str) -> None:
    _platform_ctx.set(platform)


def get_platform() -> str:
    return _platform_ctx.get()
