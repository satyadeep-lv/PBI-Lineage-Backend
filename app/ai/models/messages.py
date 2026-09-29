from typing import Any

from pydantic import BaseModel, Field

from app.ai.models.enums import MessageRole


class ModelToolCall(BaseModel):
    """One tool the model asked to run, provider-neutral."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ModelMessage(BaseModel):
    role: MessageRole
    content: str = ""

    # Set on an assistant turn that requested tools, and on the tool turn
    # that answers one.
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
