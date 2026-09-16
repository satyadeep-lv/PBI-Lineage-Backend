import pytest

from app.ai.composition.grounded_composer import ComposerFailure, compose
from app.ai.composition.grounding_validator import (
    GroundedResponseValidator,
    GroundingRejectedError,
)
from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import AIAnswerStatus, AudienceType
from app.ai.models.evidence import EvidenceBundle
from app.ai.models.responses import ModelResponse, TokenUsage
from app.ai.services.ai_service import AIService
from app.ai.tools import measure_tools
from app.core.config import Settings
from tests.unit.ai_fixtures import (
    GROSS_MARGIN_DAX,
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_semantic_model,
)


def _bundle_with_definition() -> EvidenceBundle:
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
    evidence = measure_tools.get_measure_definition(context)
    numbered = [
        item.model_copy(update={"evidence_id": f"E{index + 1}"})
        for index, item in enumerate(evidence)
    ]
    return EvidenceBundle(
        question="Explain Gross Margin %",
        context=context,
        evidence=numbered,
        can_answer=True,
        status=AIAnswerStatus.ANSWERED,
        agent="measure_agent",
    )


class _ScriptedGateway:
    """A ModelGateway double that returns fixed, test-controlled content."""

    def __init__(self, content: str) -> None:
        self._content = content

    async def generate(self, request):
        return ModelResponse(
            content=self._content,
            provider="fake",
            model="fake-model",
            usage=TokenUsage(total_tokens=10),
            finish_reason="stop",
        )

    async def stream(self, request):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_compose_and_validate_accepts_well_formed_claims():
    bundle = _bundle_with_definition()
    gateway = _ScriptedGateway(
        '{"summary": "Gross Margin % divides Gross Profit by Net Sales.", '
        '"claims": [{"text": "Gross Margin % = DIVIDE([Gross Profit], '
        '[Net Sales])", "evidence_ids": ["E1"]}]}'
    )

    composed, model_response = await compose(
        gateway, bundle, audience=AudienceType.DEVELOPER
    )
    claims = GroundedResponseValidator.validate(composed.claims, bundle)

    assert len(claims) == 1
    assert claims[0].evidence_ids == ["E1"]
    assert model_response.provider == "fake"


@pytest.mark.asyncio
async def test_composer_fails_closed_on_hallucinated_claim_with_no_evidence():
    """Pydantic's min_length=1 on GroundedClaim.evidence_ids means a claim
    with an empty evidence_ids list is rejected at parse time already --
    the composer fails closed rather than stripping the citation and
    keeping the sentence."""
    bundle = _bundle_with_definition()
    gateway = _ScriptedGateway(
        '{"summary": "...", "claims": [{"text": "This measure also '
        'affects Finance Dashboard.", "evidence_ids": []}]}'
    )

    with pytest.raises(ComposerFailure):
        await compose(gateway, bundle, audience=AudienceType.GENERAL)


@pytest.mark.asyncio
async def test_validator_rejects_claim_citing_unknown_evidence_id():
    bundle = _bundle_with_definition()
    gateway = _ScriptedGateway(
        '{"summary": "...", "claims": [{"text": "Gross Margin % depends '
        'on something.", "evidence_ids": ["E999"]}]}'
    )

    composed, _ = await compose(gateway, bundle, audience=AudienceType.GENERAL)

    with pytest.raises(GroundingRejectedError):
        GroundedResponseValidator.validate(composed.claims, bundle)


@pytest.mark.asyncio
async def test_composer_fails_closed_on_non_json_response():
    bundle = _bundle_with_definition()
    gateway = _ScriptedGateway("I think Gross Margin is probably fine.")

    with pytest.raises(ComposerFailure):
        await compose(gateway, bundle, audience=AudienceType.GENERAL)


@pytest.mark.asyncio
async def test_service_falls_back_to_deterministic_renderer_on_bad_citation():
    bundle = _bundle_with_definition()
    gateway = _ScriptedGateway(
        '{"summary": "...", "claims": [{"text": "hallucinated fact", '
        '"evidence_ids": ["E999"]}]}'
    )
    service = AIService(settings=Settings(ai_enabled=True), gateway=gateway)

    answer, claims, usage, fallback_used = await service._compose_grounded_answer(
        bundle,
        audience=AudienceType.DEVELOPER,
    )

    assert fallback_used is True
    assert claims == []
    assert usage is None
    # The exact DAX, straight from the deterministic service, still reaches
    # the user even though the model's composed answer was rejected.
    assert GROSS_MARGIN_DAX in answer


@pytest.mark.asyncio
async def test_service_uses_grounded_answer_when_valid():
    bundle = _bundle_with_definition()
    gateway = _ScriptedGateway(
        '{"summary": "Gross Margin % divides Gross Profit by Net Sales.", '
        '"claims": [{"text": "Gross Margin % = DIVIDE([Gross Profit], '
        '[Net Sales])", "evidence_ids": ["E1"]}]}'
    )
    service = AIService(settings=Settings(ai_enabled=True), gateway=gateway)

    answer, claims, usage, fallback_used = await service._compose_grounded_answer(
        bundle,
        audience=AudienceType.DEVELOPER,
    )

    assert fallback_used is False
    assert len(claims) == 1
    assert usage is not None
    assert usage.provider == "fake"
