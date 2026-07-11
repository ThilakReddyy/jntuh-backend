from typing import Any

import httpx

from chatbot.errors import (
    ChatbotNotConfiguredError,
    ChatbotResponseError,
    ChatbotUpstreamError,
    ChatbotUpstreamTimeoutError,
)


class OpenAICompatibleProvider:
    """Small chat-completions client with no provider-specific SDK dependency."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None,
        model: str | None,
        timeout_seconds: float,
        max_output_tokens: int,
    ):
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.strip().rstrip("/") if base_url else None
        self.model = model.strip() if model else None
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    @property
    def configured(self) -> bool:
        if not (self.api_key and self.base_url and self.model):
            return False
        try:
            url = httpx.URL(self.base_url)
        except (TypeError, ValueError):
            return False
        return url.scheme in ("http", "https") and bool(url.host)

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not self.configured:
            raise ChatbotNotConfiguredError(
                "Chatbot provider is not configured; set non-empty "
                "CHATBOT_API_KEY and CHATBOT_MODEL values and a valid HTTP(S) "
                "CHATBOT_BASE_URL"
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": self.max_output_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ChatbotUpstreamTimeoutError(
                "The chatbot model provider timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise ChatbotUpstreamError(
                "The chatbot model provider could not be reached"
            ) from exc

        if response.status_code >= 400:
            raise ChatbotUpstreamError(
                f"The chatbot model provider returned HTTP {response.status_code}"
            )

        try:
            body = response.json()
            message = body["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ChatbotResponseError(
                "The chatbot model provider returned a malformed response"
            ) from exc

        if not isinstance(message, dict):
            raise ChatbotResponseError(
                "The chatbot model provider returned a malformed message"
            )
        return message
