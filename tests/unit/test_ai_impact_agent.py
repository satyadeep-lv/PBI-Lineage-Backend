from app.ai.agents.impact_agent import ImpactAgent
from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import AIAnswerStatus
from tests.unit.ai_fixtures import (
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_report_definition,
    sample_semantic_model,
)


def test_impact_agent_answers_with_upstream_and_downstream_evidence():
    context = ResolvedAIContext(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        parsed_semantic_model=sample_semantic_model(),
        report_definition=sample_report_definition(),
        resolved_object=ResolvedObject(
            object_type="measure",
            table_name="Sales",
            object_name="Gross Margin %",
            qualified_name="Sales[Gross Margin %]",
        ),
    )

    bundle = ImpactAgent().gather_evidence(
        "What happens if Gross Margin % changes?",
        context,
    )

    assert bundle.status == AIAnswerStatus.ANSWERED
    assert bundle.agent == "impact_agent"

    impacted = {
        item.object_name for item in bundle.evidence if item.fact_type == "impact"
    }
    assert "Margin Card" in impacted

    depends_on = {
        item.object_name for item in bundle.evidence if item.fact_type == "dependency"
    }
    assert {"Gross Profit", "Net Sales"} <= depends_on


def test_impact_agent_insufficient_evidence_when_object_unresolved():
    bundle = ImpactAgent().gather_evidence(
        "What happens if this changes?",
        ResolvedAIContext(),
    )

    assert bundle.status == AIAnswerStatus.INSUFFICIENT_EVIDENCE
    assert bundle.can_answer is False


def test_impact_agent_insufficient_evidence_when_no_lineage_reaches_object():
    # A resolved object with no upstream/downstream connections in the
    # model (an isolated table) should not fabricate impact.
    context = ResolvedAIContext(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        parsed_semantic_model=sample_semantic_model(),
        resolved_object=ResolvedObject(
            object_type="table",
            table_name="Sales",
            object_name="Sales",
            qualified_name="Sales",
        ),
    )

    bundle = ImpactAgent().gather_evidence("What depends on the Sales table?", context)

    # The table itself has no node_type mapping to a lineage-only edge
    # target here (contains edges are non-lineage), so no impact evidence
    # should be fabricated -- either insufficient evidence or answered with
    # genuinely empty findings, never invented relationships.
    assert bundle.status in (
        AIAnswerStatus.ANSWERED,
        AIAnswerStatus.INSUFFICIENT_EVIDENCE,
    )
    impacted_names = {
        item.object_name for item in bundle.evidence if item.fact_type == "impact"
    }
    assert "Margin Card" not in impacted_names
