from utils.logger import logger
import json
import time
from dataclasses import dataclass
from typing import Any

from config.mcp import MCP_INCLUDE_OPERATIONS
from utils.telemetry import log_failure, trace_function


MAX_TOOL_RESULT_CHARACTERS = 40000


@dataclass(frozen=True)
class ToolExecution:
    content: str
    success: bool
    duration_ms: int


class MCPToolGateway:
    """Expose and execute only the tools already configured on FastApiMCP."""

    @trace_function
    def __init__(self, mcp: Any):
        self._mcp = mcp
        self._tools = {
            tool.name: tool
            for tool in mcp.tools
            if self._is_allowed_read_only_operation(tool.name)
        }

    @trace_function
    def _is_allowed_read_only_operation(self, name: str) -> bool:
        operation = self._mcp.operation_map.get(name)
        return (
            name in MCP_INCLUDE_OPERATIONS
            and isinstance(operation, dict)
            and operation.get("method", "").lower() == "get"
        )

    @property
    @trace_function
    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }
            for tool in self._tools.values()
        ]

    @trace_function
    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecution:
        if name not in self._tools or not self._is_allowed_read_only_operation(name):
            logger.warning("Chatbot tool call skipped: tool is unavailable or outside the read-only allowlist")
            return ToolExecution(
                content=json.dumps({"error": "Tool is not available"}),
                success=False,
                duration_ms=0,
            )

        started = time.perf_counter()
        try:
            result = await self._mcp._execute_api_tool(
                client=self._mcp._http_client,
                tool_name=name,
                arguments=arguments,
                operation_map={name: self._mcp.operation_map[name]},
            )
            content = "\n".join(
                item.text for item in result if isinstance(getattr(item, "text", None), str)
            )
            if not content:
                logger.warning("Chatbot tool call returned no text result")
                content = json.dumps({"error": "Tool returned no text result"})
                success = False
            else:
                success = True
        except Exception as error:
            # Endpoint details may include internal response bodies; keep them out of
            # both the model context and the public API response.
            content = json.dumps({"error": "Tool call failed"})
            log_failure("chatbot.execute_tool", error)
            success = False

        if len(content) > MAX_TOOL_RESULT_CHARACTERS:
            logger.warning("Chatbot tool output truncated at the configured size limit")
            marker = "\n[tool result truncated]"
            content = content[: MAX_TOOL_RESULT_CHARACTERS - len(marker)] + marker
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        return ToolExecution(content, success, duration_ms)
