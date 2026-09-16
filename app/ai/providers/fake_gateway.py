from collections.abc import AsyncIterator

from app.ai.models.enums import MessageRole
from app.ai.models.requests import ModelRequest
from app.ai.models.responses import ModelChunk, ModelResponse, TokenUsage

_PROVIDER_NAME = "fake"


class FakeModelGateway:
    """Deterministic, network-free ModelGateway.

    Selected automatically when AI_PROVIDER=fake (the default), so an
    unconfigured deployment still has a working, fully testable /ai/chat
    round trip. Also used directly by tests instead of monkeypatching a
    real provider SDK.
    """

    def __init__(self, *, model: str = "fake-model") -> None:
        self._model = model

    @staticmethod
    def _last_user_message(request: ModelRequest) -> str:
        for message in reversed(request.messages):
            if message.role == MessageRole.USER:
                return message.content

        return ""

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        user_message = self._last_user_message(request)
        content = f"[fake-ai response] {user_message}".strip()

        usage = TokenUsage(
            prompt_tokens=len(user_message.split()),
            completion_tokens=len(content.split()),
            total_tokens=len(user_message.split()) + len(content.split()),
        )

        return ModelResponse(
            content=content,
            provider=_PROVIDER_NAME,
            model=request.model or self._model,
            usage=usage,
            finish_reason="stop",
        )

    async def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelChunk]:
        response = await self.generate(request)
        words = response.content.split(" ")

        for index, word in enumerate(words):
            is_last = index == len(words) - 1

            yield ModelChunk(
                delta=word if index == 0 else f" {word}",
                finished=is_last,
                usage=response.usage if is_last else None,
            )
