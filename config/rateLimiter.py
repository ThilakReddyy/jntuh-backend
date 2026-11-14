"""Application rate limiting.

A single shared `Limiter` instance backed by Redis so limits are enforced
consistently across every uvicorn worker / container. Behind Cloudflare and a
reverse proxy, `request.client.host` is the proxy IP, so the key function
resolves the real client IP from `CF-Connecting-IP` / `X-Forwarded-For` and
falls back to the socket peer.

The limiter fails open: if Redis is unreachable it swallows the error and uses
an in-memory fallback, so a Redis blip degrades rate limiting rather than
breaking the API.
"""

from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import Response

from config.settings import REDIS_URL

# Paths under these prefixes bypass the limiter entirely. The MCP server is
# mounted as a sub-app via FastApiMCP.mount_http() — slowapi 0.1.10 still
# applies default_limits to it through the outer middleware, so we exempt it
# explicitly rather than relying on the "no endpoint → skipped" assumption.
EXEMPT_PATH_PREFIXES = ("/mcp",)


def get_client_ip(request: Request) -> str:
    """Resolve the originating client IP when running behind Cloudflare / a proxy."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First entry is the original client; the rest are proxy hops.
        return forwarded_for.split(",")[0].strip()

    return get_remote_address(request)


# Default applied to every route via ExemptingSlowAPIMiddleware. Paths under
# EXEMPT_PATH_PREFIXES (currently only `/mcp`) bypass the limiter entirely —
# slowapi 0.1.10 does NOT auto-skip mounted sub-apps the way the docs imply, so
# we exempt them explicitly. Routes that declare their own @limiter.limit(...)
# opt out of this default and enforce only their stricter limit.
DEFAULT_LIMIT = "30/minute"

limiter = Limiter(
    key_func=get_client_ip,
    default_limits=[DEFAULT_LIMIT],
    storage_uri=REDIS_URL,
    strategy="fixed-window",
    headers_enabled=True,  # adds X-RateLimit-* and Retry-After response headers
    swallow_errors=True,  # fail open if the storage backend errors
    in_memory_fallback_enabled=True,  # fall back to memory if Redis is down
    key_prefix="rl",
)


class ExemptingSlowAPIMiddleware(SlowAPIMiddleware):
    """SlowAPIMiddleware that short-circuits for `EXEMPT_PATH_PREFIXES`."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith(EXEMPT_PATH_PREFIXES):
            return await call_next(request)
        return await super().dispatch(request, call_next)
