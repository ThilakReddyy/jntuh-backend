import asyncio
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from chatbot.errors import (
    ChatbotNotConfiguredError,
    ChatbotResponseError,
    ChatbotUpstreamError,
    ChatbotUpstreamTimeoutError,
)
from chatbot.provider import OpenAICompatibleProvider
from chatbot.schemas import ChatRequest
from chatbot.service import ChatbotService
from chatbot.tools import MCPToolGateway, ToolExecution


class FakeProvider:
    model = "test-model"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def complete(self, messages, tools):
        self.calls.append((messages, tools))
        return next(self.responses)


class FakeGateway:
    definitions = [
        {
            "type": "function",
            "function": {
                "name": "get_backlogs",
                "description": "Get backlogs",
                "parameters": {"type": "object"},
            },
        }
    ]

    def __init__(self):
        self.calls = []

    async def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return ToolExecution('{"totalBacklogs": 0}', True, 12)


def test_agent_executes_allowlisted_tool_then_synthesizes_answer():
    provider = FakeProvider(
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "get_backlogs",
                            "arguments": '{"rollNumber":"22XX1A0501"}',
                        },
                    }
                ],
            },
            {"content": "You currently have no backlogs."},
        ]
    )
    gateway = FakeGateway()
    service = ChatbotService(
        provider, gateway, max_iterations=4, max_tool_calls=3
    )

    response = asyncio.run(
        service.chat(ChatRequest(message="Do I have backlogs?"))
    )

    assert response.answer == "You currently have no backlogs."
    assert gateway.calls == [("get_backlogs", {"rollNumber": "22XX1A0501"})]
    assert response.metadata.iterations == 2
    assert response.metadata.tool_calls[0].success is True
    assert provider.calls[1][0][-1]["role"] == "tool"


def test_agent_rejects_malformed_tool_arguments():
    provider = FakeProvider(
        [
            {
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "get_backlogs",
                            "arguments": "not-json",
                        },
                    }
                ]
            }
        ]
    )
    service = ChatbotService(
        provider, FakeGateway(), max_iterations=3, max_tool_calls=2
    )

    with pytest.raises(ChatbotResponseError, match="malformed tool call"):
        asyncio.run(service.chat(ChatRequest(message="Check my result")))


def test_agent_enforces_tool_call_budget_before_parsing_or_execution():
    provider = FakeProvider(
        [
            {
                "tool_calls": [
                    {"malformed": True},
                    {"also": "malformed"},
                    {"still": "malformed"},
                ]
            }
        ]
    )
    gateway = FakeGateway()
    service = ChatbotService(provider, gateway, max_iterations=3, max_tool_calls=2)

    with pytest.raises(ChatbotResponseError, match="tool call limit"):
        asyncio.run(service.chat(ChatRequest(message="Check my result")))

    assert gateway.calls == []


def test_gateway_blocks_operations_outside_shared_mcp_allowlist():
    async def fail_if_called(**kwargs):
        raise AssertionError("executor must not be called")

    mcp = SimpleNamespace(
        tools=[
            SimpleNamespace(
                name="hard_refresh",
                description="destructive",
                inputSchema={"type": "object"},
            )
        ],
        operation_map={"hard_refresh": {}},
        _http_client=object(),
        _execute_api_tool=fail_if_called,
    )
    gateway = MCPToolGateway(mcp)

    assert gateway.definitions == []
    result = asyncio.run(gateway.execute("hard_refresh", {}))
    assert result.success is False
    assert "not available" in result.content


def test_gateway_blocks_non_read_only_operation_even_when_name_is_allowlisted():
    async def fail_if_called(**kwargs):
        raise AssertionError("executor must not be called")

    mcp = SimpleNamespace(
        tools=[
            SimpleNamespace(
                name="get_backlogs",
                description="Unexpected write operation",
                inputSchema={"type": "object"},
            )
        ],
        operation_map={"get_backlogs": {"method": "post"}},
        _http_client=object(),
        _execute_api_tool=fail_if_called,
    )
    gateway = MCPToolGateway(mcp)

    assert gateway.definitions == []
    result = asyncio.run(gateway.execute("get_backlogs", {}))
    assert result.success is False


def test_request_rejects_system_roles_and_oversized_conversations():
    with pytest.raises(ValidationError):
        ChatRequest(message="hello", messages=[{"role": "system", "content": "x"}])

    with pytest.raises(ValidationError, match="16000 character limit"):
        ChatRequest(
            message="x" * 4000,
            messages=[
                {"role": "user", "content": "x" * 4000},
                {"role": "assistant", "content": "x" * 4000},
                {"role": "user", "content": "x" * 4000},
                {"role": "assistant", "content": "x"},
            ],
        )


def test_unconfigured_provider_fails_without_an_upstream_request():
    provider = OpenAICompatibleProvider(
        api_key=None,
        base_url=None,
        model=None,
        timeout_seconds=30,
        max_output_tokens=800,
    )

    with pytest.raises(ChatbotNotConfiguredError, match="CHATBOT_API_KEY"):
        asyncio.run(provider.complete([{"role": "user", "content": "hi"}], []))


@pytest.mark.parametrize("base_url", [None, "   ", "not-a-url", "ftp://example.com"])
def test_provider_rejects_missing_or_invalid_base_url(base_url):
    provider = OpenAICompatibleProvider(
        api_key="key",
        base_url=base_url,
        model="model",
        timeout_seconds=30,
        max_output_tokens=800,
    )

    with pytest.raises(ChatbotNotConfiguredError, match=r"valid HTTP\(S\)"):
        asyncio.run(provider.complete([{"role": "user", "content": "hi"}], []))


def test_provider_maps_timeout_and_http_failures(monkeypatch):
    class FakeClient:
        def __init__(self, *, error, **kwargs):
            self.error = error

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            raise self.error

    provider = OpenAICompatibleProvider(
        api_key="key",
        base_url="https://example.com/v1",
        model="model",
        timeout_seconds=30,
        max_output_tokens=800,
    )

    monkeypatch.setattr(
        "chatbot.provider.httpx.AsyncClient",
        lambda **kwargs: FakeClient(error=httpx.ReadTimeout("slow")),
    )
    with pytest.raises(ChatbotUpstreamTimeoutError, match="timed out"):
        asyncio.run(provider.complete([{"role": "user", "content": "hi"}], []))

    monkeypatch.setattr(
        "chatbot.provider.httpx.AsyncClient",
        lambda **kwargs: FakeClient(error=httpx.ConnectError("down")),
    )
    with pytest.raises(ChatbotUpstreamError, match="could not be reached"):
        asyncio.run(provider.complete([{"role": "user", "content": "hi"}], []))
