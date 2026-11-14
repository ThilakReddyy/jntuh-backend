"""Prometheus instrumentation for MCP JSON-RPC traffic.

The /metrics endpoint exposed by prometheus_fastapi_instrumentator already
captures HTTP requests at /mcp, but every MCP tool call is a single POST to
/mcp — so without this layer we cannot distinguish getAcademicResult from
getBacklogs, nor see per-tool latency or error rates.

instrument_mcp() wraps each handler stored in mcp.server.request_handlers so
every MCP request (CallToolRequest, ListToolsRequest, InitializeRequest, ...)
emits counter + histogram samples labeled by JSON-RPC method and, for tool
calls, by the tool name.
"""

import time
from typing import Any, Awaitable, Callable

from prometheus_client import Counter, Gauge, Histogram

from utils.logger import logger

MCP_CALLS = Counter(
    "mcp_calls_total",
    "Total MCP JSON-RPC requests handled, by method/tool/status.",
    labelnames=("method", "tool", "status"),
)

MCP_CALL_DURATION = Histogram(
    "mcp_call_duration_seconds",
    "Latency of MCP JSON-RPC request handlers in seconds.",
    labelnames=("method", "tool"),
)

MCP_CALLS_IN_PROGRESS = Gauge(
    "mcp_calls_in_progress",
    "In-flight MCP JSON-RPC requests.",
    labelnames=("method", "tool"),
)


def _extract_tool_name(req: Any) -> str:
    """Return the tool name for a CallToolRequest, else ''."""
    params = getattr(req, "params", None)
    name = getattr(params, "name", None) if params is not None else None
    return name if isinstance(name, str) else ""


def _is_error_result(method: str, result: Any) -> bool:
    """Detect tool-call errors that are returned (not raised)."""
    if method != "CallToolRequest":
        return False
    inner = getattr(result, "root", None)
    return bool(getattr(inner, "isError", False))


def instrument_mcp(mcp: Any) -> None:
    """Wrap mcp.server.request_handlers with Prometheus instrumentation.

    Call exactly once after FastApiMCP construction (handlers are registered
    in __init__). Calling on an already-instrumented server double-wraps and
    double-counts.
    """
    handlers: dict[type, Callable[[Any], Awaitable[Any]]] = mcp.server.request_handlers

    for request_type, handler in list(handlers.items()):
        method = getattr(request_type, "__name__", str(request_type))
        handlers[request_type] = _wrap(handler, method)

    logger.info(f"MCP metrics installed for {len(handlers)} request handler(s).")


def _wrap(
    handler: Callable[[Any], Awaitable[Any]], method: str
) -> Callable[[Any], Awaitable[Any]]:
    async def wrapped(req: Any) -> Any:
        tool = _extract_tool_name(req)
        MCP_CALLS_IN_PROGRESS.labels(method=method, tool=tool).inc()
        start = time.perf_counter()
        status = "success"
        try:
            result = await handler(req)
            if _is_error_result(method, result):
                status = "error"
            return result
        except Exception:
            status = "error"
            raise
        finally:
            MCP_CALL_DURATION.labels(method=method, tool=tool).observe(
                time.perf_counter() - start
            )
            MCP_CALLS_IN_PROGRESS.labels(method=method, tool=tool).dec()
            MCP_CALLS.labels(method=method, tool=tool, status=status).inc()

    return wrapped
