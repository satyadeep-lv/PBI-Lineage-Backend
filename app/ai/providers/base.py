from collections.abc import AsyncIterator
from typing import Protocol

from app.ai.models.requests import ModelRequest
from app.ai.models.responses import ModelChunk, ModelResponse


class ModelGateway(Protocol):
    """Provider-neutral contract every AI provider adapter must satisfy.

    Agents and services depend only on this Protocol, never on a specific
    vendor SDK. Swapping providers is a configuration change
    (AI_PROVIDER/AI_MODEL), not a code change.
    """

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse: ...

    def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelChunk]: ...
