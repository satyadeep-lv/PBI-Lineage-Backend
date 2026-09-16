from app.ai.agents.report_agent import ReportAgent
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from tests.unit.ai_fixtures import (
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_report_definition,
    sample_semantic_model,
)


def test_report_agent_answers_with_full_evidence_chain():
    context = ResolvedAIContext(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        parsed_semantic_model=sample_semantic_model(),
        report_definition=sample_report_definition(),
    )

    bundle = ReportAgent().gather_evidence(
        "Explain this report and where its data comes from",
        context,
    )

    assert bundle.status == AIAnswerStatus.ANSWERED
    assert bundle.agent == "report_agent"

    fact_types = {item.fact_type for item in bundle.evidence}
    object_types = {item.object_type for item in bundle.evidence}

    assert "definition" in fact_types  # report summary + semantic model details
    assert "usage" in fact_types  # visuals
    assert "source" in fact_types  # physical sources
    assert "report" in object_types
    assert "visual" in object_types
    assert "physical_source" in object_types


def test_report_agent_insufficient_evidence_without_report_definition():
    bundle = ReportAgent().gather_evidence(
        "Explain this report",
        ResolvedAIContext(),
    )

    assert bundle.status == AIAnswerStatus.INSUFFICIENT_EVIDENCE
    assert bundle.can_answer is False
    assert bundle.evidence == []
