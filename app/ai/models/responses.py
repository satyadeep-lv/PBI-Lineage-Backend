from pydantic import BaseModel, Field


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
    conversation_id: str | None = None
    answer: str
    agent: str | None = None
    evidence: list[dict] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    usage: AIUsage
