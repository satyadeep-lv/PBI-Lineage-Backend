import pytest

from app.ai.models.requests import AIChatRequest
from app.ai.providers.fake_gateway import FakeModelGateway
from app.ai.services.ai_service import AIService
from app.core.config import Settings
from app.core.exceptions import AIDisabledError, AIProviderUnavailableError


@pytest.mark.asyncio
async def test_generate_raises_when_ai_disabled():
    settings = Settings(ai_enabled=False)
    service = AIService(
        settings=settings,
        gateway=FakeModelGateway(),
    )

    with pytest.raises(AIDisabledError):
        await service.generate(
            AIChatRequest(message="Explain Gross Margin"),
        )


@pytest.mark.asyncio
async def test_status_reports_configuration_without_secrets():
    settings = Settings(
        ai_enabled=True,
        ai_provider="fake",
        ai_model="fake-model",
        ai_streaming_enabled=True,
    )
    service = AIService(
        settings=settings,
        gateway=FakeModelGateway(model="fake-model"),
    )

    status = service.status()

    assert status.enabled is True
    assert status.provider == "fake"
    assert status.model == "fake-model"
    assert status.streaming_enabled is True
    assert status.configured is True
    assert "key" not in status.model_dump()


@pytest.mark.asyncio
async def test_generate_returns_chat_response_with_usage():
    settings = Settings(
        ai_enabled=True,
        ai_provider="fake",
        ai_model="fake-model",
    )
    service = AIService(
        settings=settings,
        gateway=FakeModelGateway(model="fake-model"),
    )

    response = await service.generate(
        AIChatRequest(
            conversation_id="conv-1",
            message="Explain Gross Margin",
        ),
    )

    assert response.conversation_id == "conv-1"
    assert response.agent is None
    assert response.evidence == []
    assert response.suggested_questions == []
    assert response.usage.provider == "fake"
    assert response.usage.tokens > 0
    assert "Explain Gross Margin" in response.answer


@pytest.mark.asyncio
async def test_generate_propagates_gateway_errors():
    class _FailingGateway:
        async def generate(self, request):
            raise AIProviderUnavailableError()

        async def stream(self, request):
            raise NotImplementedError

    settings = Settings(ai_enabled=True)
    service = AIService(
        settings=settings,
        gateway=_FailingGateway(),
    )

    with pytest.raises(AIProviderUnavailableError):
        await service.generate(
            AIChatRequest(message="Explain Gross Margin"),
        )
