import pytest

from app.ai.agents.measure_agent import MeasureAgent
from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import AIAnswerStatus, AudienceType
from app.ai.models.requests import AIChatRequest
from app.ai.providers.litellm_gateway import (
    _load_litellm,
    reset_litellm_import_state,
)
from app.ai.services.ai_service import AIService
from app.core.config import Settings
from app.core.exceptions import AIProviderUnavailableError
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)


def _model() -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                columns=[
                    ParsedSemanticModelColumn(name="REVENUE"),
                    ParsedSemanticModelColumn(name="COST"),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Total Revenue",
                        expression="SUM('Sales'[REVENUE])",
                    ),
                    ParsedSemanticModelMeasure(
                        name="Total Cost",
                        expression="SUM('Sales'[COST])",
                    ),
                    ParsedSemanticModelMeasure(
                        name="Profit Margin %",
                        expression="DIVIDE([Total Revenue] - [Total Cost], "
                        "[Total Revenue])",
                    ),
                ],
            )
        ],
    )


def _context(measure: str) -> ResolvedAIContext:
    return ResolvedAIContext(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        parsed_semantic_model=_model(),
        resolved_object=ResolvedObject(
            object_type="measure",
            table_name="Sales",
            object_name=measure,
            qualified_name=f"Sales[{measure}]",
        ),
    )


def test_measure_evidence_covers_dax_dependencies_and_impact():
    bundle = MeasureAgent().gather_evidence(
        "Explain Profit Margin %",
        _context("Profit Margin %"),
    )

    assert bundle.status == AIAnswerStatus.ANSWERED

    by_fact = {}
    for item in bundle.evidence:
        by_fact.setdefault(str(item.fact_type), []).append(item)

    definition = by_fact["definition"][0]
    assert definition.value == (
        "DIVIDE([Total Revenue] - [Total Cost], [Total Revenue])"
    )

    # The measures this one is built on -- the cross-dependency the DAX names.
    dependency_names = {item.object_name for item in by_fact["dependency"]}
    assert {"Total Revenue", "Total Cost"} <= dependency_names
    # ...and the columns underneath them, so the source tables are reachable.
    assert {"REVENUE", "COST"} <= dependency_names


def test_a_measure_reports_what_depends_on_it():
    bundle = MeasureAgent().gather_evidence(
        "What uses Total Revenue?",
        _context("Total Revenue"),
    )

    impact = [item for item in bundle.evidence if str(item.fact_type) == "impact"]
    assert "Profit Margin %" in {item.object_name for item in impact}


@pytest.mark.asyncio
async def test_explain_answers_without_a_model_and_with_ai_disabled(monkeypatch):
    # The factual answer must not depend on a provider being configured or
    # reachable -- /chat would raise AIDisabledError here.
    service = AIService(
        settings=Settings(ai_enabled=False, ai_provider="fake"),
        powerbi_access_token="token",
        fabric_access_token="token",
    )

    async def fake_bundle(request):
        return MeasureAgent().gather_evidence(
            request.message,
            _context("Profit Margin %"),
        )

    monkeypatch.setattr(service, "build_evidence_bundle", fake_bundle)

    response = await service.explain(
        AIChatRequest(
            message="Explain Profit Margin %",
            audience=AudienceType.DEVELOPER,
        )
    )

    assert response.status == AIAnswerStatus.ANSWERED
    assert response.usage is None  # the model was never called
    assert "DIVIDE([Total Revenue] - [Total Cost], [Total Revenue])" in response.answer
    assert "Depends on" in response.answer
    assert response.evidence


def test_a_failed_litellm_import_is_remembered_briefly(monkeypatch):
    # Python does not cache failed imports, so every request re-ran litellm's
    # import and waited out its network retries (~28s measured) before the
    # deterministic fallback could kick in.
    reset_litellm_import_state()
    attempts = 0

    real_import = (
        __builtins__["__import__"]
        if isinstance(__builtins__, dict)
        else __builtins__.__import__
    )

    def failing_import(name, *args, **kwargs):
        nonlocal attempts
        if name == "litellm":
            attempts += 1
            raise OSError("certificate verify failed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", failing_import)

    for _ in range(5):
        with pytest.raises(AIProviderUnavailableError):
            _load_litellm()

    assert attempts == 1

    reset_litellm_import_state()


def test_definition_evidence_carries_a_plain_language_line():
    from app.ai.tools import measure_tools

    items = measure_tools.get_measure_definition(_context("Profit Margin %"))

    assert items[0].plain_language == (
        "Profit Margin % divides Total Revenue minus Total Cost by Total Revenue."
    )
    # The DAX itself is untouched.
    assert items[0].value == ("DIVIDE([Total Revenue] - [Total Cost], [Total Revenue])")


def test_a_visual_is_named_by_page_and_type_not_by_guid():
    from app.ai.composition.deterministic_renderer import _visual_label

    assert (
        _visual_label(
            {
                "visual_title": "Margin Card",
                "visual_type": "card",
                "page_display_name": "Overview",
            }
        )
        == "Margin Card (card) on page 'Overview'"
    )

    # An untitled visual still says what and where, rather than a GUID.
    assert (
        _visual_label(
            {
                "visual_id": "4601a0b18437df80ee432161",
                "visual_type": "barChart",
                "page_display_name": "Sales",
            }
        )
        == "barChart visual on page 'Sales'"
    )
