from unittest.mock import AsyncMock

import pytest

from app.ai.agents.measure_agent import MeasureAgent
from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import AIAnswerStatus, AudienceType
from app.ai.models.requests import AIChatRequest
from app.ai.models.responses import ModelResponse, TokenUsage
from app.ai.providers.fake_gateway import FakeModelGateway
from app.ai.services.ai_service import AIService
from app.core.config import Settings
from app.core.exceptions import AIDisabledError
from tests.unit.ai_fixtures import (
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_semantic_model,
)


class _SpyGateway:
    """Wraps a real gateway while recording whether generate() was called.

    A plain, explicit spy (rather than unittest.mock's wraps= on an
    AsyncMock) so there is no ambiguity about whether the call was actually
    intercepted -- this assertion is the single most important one in this
    suite.
    """

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped
        self.generate_called = False

    async def generate(self, request):
        self.generate_called = True
        return await self._wrapped.generate(request)

    async def stream(self, request):
        self.generate_called = True
        async for chunk in self._wrapped.stream(request):
            yield chunk


def _measure_bundle():
    context = ResolvedAIContext(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        parsed_semantic_model=sample_semantic_model(),
        resolved_object=ResolvedObject(
            object_type="measure",
            table_name="Sales",
            object_name="Gross Margin %",
            qualified_name="Sales[Gross Margin %]",
        ),
    )
    return MeasureAgent().gather_evidence("Explain Gross Margin %", context)


@pytest.mark.asyncio
async def test_generate_raises_when_ai_disabled():
    settings = Settings(ai_enabled=False)
    service = AIService(settings=settings, gateway=FakeModelGateway())

    with pytest.raises(AIDisabledError):
        await service.generate(AIChatRequest(message="Explain Gross Margin"))


@pytest.mark.asyncio
async def test_status_reports_configuration_without_secrets():
    settings = Settings(
        ai_enabled=True,
        ai_provider="fake",
        ai_model="fake-model",
        ai_streaming_enabled=True,
    )
    service = AIService(settings=settings, gateway=FakeModelGateway(model="fake-model"))

    status = service.status()

    assert status.enabled is True
    assert status.provider == "fake"
    assert status.model == "fake-model"
    assert status.streaming_enabled is True
    assert status.configured is True
    assert "key" not in status.model_dump()


@pytest.mark.asyncio
async def test_no_evidence_gate_never_calls_the_gateway():
    """The core rule: no verified evidence -> no factual answer, and the
    model is never called to guess. This is the single most important
    assertion in this test suite."""
    spy_gateway = _SpyGateway(FakeModelGateway())
    settings = Settings(ai_enabled=True, ai_provider="fake")
    service = AIService(settings=settings, gateway=spy_gateway)

    # No context at all -> nothing can be resolved -> out_of_scope /
    # insufficient_evidence, whichever the router picks, but never answered.
    response = await service.generate(
        AIChatRequest(message="What's the weather today?"),
    )

    assert response.status != AIAnswerStatus.ANSWERED
    assert response.usage is None
    assert spy_gateway.generate_called is False


@pytest.mark.asyncio
async def test_no_evidence_gate_for_unresolved_object_never_calls_gateway():
    spy_gateway = _SpyGateway(FakeModelGateway())
    settings = Settings(ai_enabled=True, ai_provider="fake")
    service = AIService(settings=settings, gateway=spy_gateway)

    response = await service.generate(
        AIChatRequest(
            message="What reports use XYZ Revenue Forecast Measure?",
            context={
                "workspace_id": WORKSPACE_ID,
                "semantic_model_id": SEMANTIC_MODEL_ID,
                "object_type": "measure",
                "object_name": "XYZ Revenue Forecast Measure",
            },
        ),
    )

    # No real resolver I/O was mocked, so this resolves nothing and the
    # answer must be insufficient_evidence -- never a fabricated answer.
    assert response.status != AIAnswerStatus.ANSWERED
    assert spy_gateway.generate_called is False


@pytest.mark.asyncio
async def test_persona_changes_presentation_not_evidence(monkeypatch):
    bundle = _measure_bundle()
    settings = Settings(ai_enabled=True, ai_provider="fake")
    responses = {}

    for audience in (
        AudienceType.GENERAL,
        AudienceType.BUSINESS,
        AudienceType.DEVELOPER,
    ):
        service = AIService(settings=settings, gateway=FakeModelGateway())
        monkeypatch.setattr(
            service,
            "build_evidence_bundle",
            AsyncMock(return_value=bundle),
        )
        responses[audience] = await service.generate(
            AIChatRequest(message="Explain Gross Margin %", audience=audience)
        )

    evidence_dumps = {
        audience: [item.model_dump() for item in response.evidence]
        for audience, response in responses.items()
    }
    assert (
        evidence_dumps[AudienceType.GENERAL]
        == evidence_dumps[AudienceType.BUSINESS]
        == evidence_dumps[AudienceType.DEVELOPER]
    )

    # Developer presentation includes internal object ids; general does not.
    assert (
        responses[AudienceType.DEVELOPER].answer
        != responses[AudienceType.GENERAL].answer
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["openai", "anthropic", "gemini"])
async def test_same_pipeline_works_across_simulated_providers(provider_name):
    """Same agents/tools/composer/validator, only the injected gateway
    changes -- proving provider independence without live credentials."""

    class _FakeProviderGateway:
        def __init__(self, provider: str) -> None:
            self.provider = provider

        async def generate(self, request):
            return ModelResponse(
                content=(
                    '{"summary": "Gross Margin % divides Gross Profit by '
                    'Net Sales.", "claims": [{"text": "Gross Margin % = '
                    'DIVIDE([Gross Profit], [Net Sales])", '
                    '"evidence_ids": ["E1"]}]}'
                ),
                provider=self.provider,
                model=f"{self.provider}-model",
                usage=TokenUsage(total_tokens=5),
                finish_reason="stop",
            )

        async def stream(self, request):
            raise NotImplementedError

    bundle = _measure_bundle()
    settings = Settings(ai_enabled=True)
    service = AIService(
        settings=settings,
        gateway=_FakeProviderGateway(provider_name),
    )

    answer, claims, usage, fallback_used = await service._compose_grounded_answer(
        bundle,
        audience=AudienceType.GENERAL,
    )

    assert fallback_used is False
    assert len(claims) == 1
    assert usage is not None
    assert usage.provider == provider_name
    assert "DIVIDE" in answer or "Gross Margin" in answer
