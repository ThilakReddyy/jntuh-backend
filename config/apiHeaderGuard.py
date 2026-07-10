"""Gate API routes behind a required `X-Api-Key` request header.

Every request must carry a non-empty `X-Api-Key` header or it is rejected with
403 before reaching the route (or the rate limiter). If the optional
`API_ACCESS_KEY` env var is set, the header value must also match it exactly;
when unset, any non-empty value passes (presence-only check).

Requests from the JNTUH Connect Android app are allowed WITHOUT the header,
recognised by User-Agent: Retrofit/OkHttp sends `okhttp/<version>` and the
app's raw HttpURLConnection health probe sends `Dalvik/... (Linux; U; Android
...)`. A User-Agent is trivially spoofable, so like the header itself this
only blocks casual direct hits, not a determined caller.

Exempt from the check:
- `/mcp` — the MCP sub-app mounted by FastApiMCP; MCP clients cannot be asked
  to send custom headers.
- `/metrics` — scraped by Prometheus, which sends no custom headers.
- `/docs`, `/redoc`, `/openapi.json` — interactive docs pages.
- `/` and `/connect` — static landing/setup pages.
- `OPTIONS` requests — CORS preflights never carry custom headers; CORS sits
  outermost and normally answers them, this is just a defensive skip.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Loaded via config.settings so load_dotenv() has run before we read the env.
from config.settings import API_ACCESS_KEY

API_KEY_HEADER = "X-Api-Key"

GUARD_EXEMPT_PATH_PREFIXES = ("/mcp", "/metrics", "/docs", "/redoc", "/openapi.json")
GUARD_EXEMPT_EXACT_PATHS = ("/", "/connect")

# User-Agent prefixes (lower-cased) that bypass the header check — the JNTUH
# Connect Android app: OkHttp/Retrofit ("okhttp/4.12.0") and Android's
# HttpURLConnection ("Dalvik/2.1.0 (Linux; U; Android 14; ...)").
ALLOWED_USER_AGENT_PREFIXES = ("okhttp/", "dalvik/")


class ApiKeyHeaderMiddleware(BaseHTTPMiddleware):
    """Reject requests missing the `X-Api-Key` header outside exempt paths."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or path in GUARD_EXEMPT_EXACT_PATHS
            or path.startswith(GUARD_EXEMPT_PATH_PREFIXES)
        ):
            return await call_next(request)

        user_agent = request.headers.get("User-Agent", "").lower()
        if user_agent.startswith(ALLOWED_USER_AGENT_PREFIXES):
            return await call_next(request)

        provided = request.headers.get(API_KEY_HEADER)
        if not provided or (API_ACCESS_KEY and provided != API_ACCESS_KEY):
            return JSONResponse(
                status_code=403,
                content={"detail": "Authentication failed"},
            )

        return await call_next(request)
