from typing import Any

from pydantic import BaseModel, Field

from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceItem, GroundedClaim
from app.ai.models.messages import ModelToolCall


class AIToolCall(BaseModel):
    """One read-only tool call made while answering."""

    round: int
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    evidence_count: int = 0
    duration_ms: int = 0
    status: str


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelResponse(BaseModel):
    """Provider-neutral response returned by a ModelGateway implementation."""

    content: str
    provider: str
    model: str
    usage: TokenUsage
    finish_reason: str | None = None

    # Present when the model asked to run tools instead of answering.
    tool_calls: list[ModelToolCall] = Field(default_factory=list)


class ModelChunk(BaseModel):
    """One streamed increment from ModelGateway.stream()."""

    delta: str
    finished: bool = False
    usage: TokenUsage | None = None


class AIStatusResponse(BaseModel):
    enabled: bool
    provider: str
    model: str
    streaming_enabled: bool
    configured: bool


class AIUsage(BaseModel):
    provider: str
    model: str
    tokens: int


class AIChatResponse(BaseModel):
    conversation_id: str

    status: AIAnswerStatus

    answer: str

    claims: list[GroundedClaim] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)

    agent: str | None = None
    suggested_questions: list[str] = Field(default_factory=list)

    # Which read-only tools ran, in order, when the model drove the answer.
    # Empty on the deterministic path, where no tool selection took place.
    tool_trace: list[AIToolCall] = Field(default_factory=list)

    # None when the model was never called (e.g. insufficient_evidence).
    usage: AIUsage | None = None
