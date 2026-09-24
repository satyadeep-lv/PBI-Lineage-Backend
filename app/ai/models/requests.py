from typing import Any

from pydantic import BaseModel, Field

from app.ai.models.enums import AudienceType
from app.ai.models.messages import ModelMessage


class ModelRequest(BaseModel):
    """Provider-neutral request passed to a ModelGateway implementation."""

    messages: list[ModelMessage]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None

    # JSON-Schema tool definitions the model may call, and an optional
    # nudge to force a tool on the first round.
    tools: list[dict[str, Any]] = Field(default_factory=list)
    require_tool: bool = False


class AIChatContext(BaseModel):
    """Lightweight UI context identifiers.

    These are accepted and validated for shape in B1 but are not yet
    resolved against authorized data or used to select a tool/agent —
    that lands in B2/B3. IDs are never trusted as authoritative on their
    own; future phases must still resolve them through the caller's own
    authenticated Power BI/Fabric/Snowflake access.
    """

    workspace_id: str | None = None
    report_id: str | None = None
    semantic_model_id: str | None = None
    page_id: str | None = None
    object_type: str | None = None
    object_id: str | None = None
    object_name: str | None = None


class AIChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    audience: AudienceType = AudienceType.GENERAL
    context: AIChatContext | None = None
