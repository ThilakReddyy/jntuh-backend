class ChatbotError(Exception):
    """Base class for expected chatbot failures."""


class ChatbotNotConfiguredError(ChatbotError):
    """Raised when required provider settings are absent."""


class ChatbotUpstreamError(ChatbotError):
    """Raised when the configured model provider fails."""


class ChatbotUpstreamTimeoutError(ChatbotUpstreamError):
    """Raised when the configured model provider times out."""


class ChatbotResponseError(ChatbotUpstreamError):
    """Raised for a malformed or unusable model response."""
