from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message content must not be blank")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    messages: list[ConversationMessage] = Field(default_factory=list, max_length=20)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @model_validator(mode="after")
    def conversation_size_is_bounded(self):
        total_characters = len(self.message) + sum(
            len(item.content) for item in self.messages
        )
        if total_characters > 16000:
            raise ValueError("conversation exceeds the 16000 character limit")
        return self


class ChatToolCallMetadata(BaseModel):
    name: str
    success: bool
    duration_ms: int = Field(ge=0)


class ChatMetadata(BaseModel):
    model: str
    iterations: int = Field(ge=1)
    tool_calls: list[ChatToolCallMetadata]
    finish_reason: str


class ChatResponse(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)
    metadata: ChatMetadata
