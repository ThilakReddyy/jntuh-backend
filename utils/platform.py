"""Best-effort client-platform classification for observability (logs/metrics
only — NOT a security boundary; reuses the same User-Agent signals that
config.apiHeaderGuard already trusts for its auth bypass)."""

from config.apiHeaderGuard import ALLOWED_USER_AGENT_PREFIXES, ALLOWED_USER_AGENTS

_BROWSER_UA_TOKENS = ("mozilla", "chrome", "safari", "firefox", "edg/")

PLATFORMS = ("android", "ios", "web", "other")


def detect_platform(user_agent: str, has_origin: bool) -> str:
    ua = (user_agent or "").lower()
    if ua in ALLOWED_USER_AGENTS:
        return "ios"
    if ua.startswith(ALLOWED_USER_AGENT_PREFIXES):
        return "android"
    # Browsers always send Origin on cross-origin fetch/XHR (the web frontend
    # calls the backend cross-origin from jntuhresults.dhethi.com); fall back
    # to a UA token check for same-origin/no-CORS edge cases.
    if has_origin or any(token in ua for token in _BROWSER_UA_TOKENS):
        return "web"
    return "other"
