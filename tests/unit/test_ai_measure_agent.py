from app.ai.agents.measure_agent import MeasureAgent
from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import AIAnswerStatus
from app.schemas.xmla_metadata import (
    XmlaSemanticModelMeasure,
    XmlaSemanticModelMetadataResponse,
    XmlaSemanticModelTable,
)
from tests.unit.ai_fixtures import (
    GROSS_MARGIN_DAX,
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_report_definition,
    sample_semantic_model,
)


def _resolved_measure_context(**overrides) -> ResolvedAIContext:
    defaults = dict(
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
    defaults.update(overrides)
    return ResolvedAIContext(**defaults)


def test_measure_agent_answers_with_definition_dependencies_and_impact():
    context = _resolved_measure_context(report_definition=sample_report_definition())

    bundle = MeasureAgent().gather_evidence("Explain Gross Margin %", context)

    assert bundle.status == AIAnswerStatus.ANSWERED
    assert bundle.can_answer is True
    assert bundle.agent == "measure_agent"

    definitions = [item for item in bundle.evidence if item.fact_type == "definition"]
    assert definitions[0].value == GROSS_MARGIN_DAX

    dependency_names = {
        item.object_name for item in bundle.evidence if item.fact_type == "dependency"
    }
    assert {"Gross Profit", "Net Sales"} <= dependency_names

    impact_names = {
        item.object_name for item in bundle.evidence if item.fact_type == "impact"
    }
    assert "Margin Card" in impact_names

    # Every evidence item was numbered.
    assert all(item.evidence_id for item in bundle.evidence)


def test_measure_agent_insufficient_evidence_when_object_unresolved():
    bundle = MeasureAgent().gather_evidence(
        "Explain this measure",
        ResolvedAIContext(),
    )

    assert bundle.status == AIAnswerStatus.INSUFFICIENT_EVIDENCE
    assert bundle.can_answer is False
    assert bundle.evidence == []


def test_measure_agent_ambiguous_when_resolution_notes_present():
    context = ResolvedAIContext(
        resolution_notes=["'Revenue' matched more than one object: A, B"]
    )

    bundle = MeasureAgent().gather_evidence("Explain Revenue", context)

    assert bundle.status == AIAnswerStatus.AMBIGUOUS
    assert bundle.can_answer is False


def test_measure_agent_insufficient_evidence_when_no_dax_definition():
    context = _resolved_measure_context(
        resolved_object=ResolvedObject(
            object_type="measure",
            table_name="Sales",
            object_name="Does Not Exist",
            qualified_name="Sales[Does Not Exist]",
        )
    )

    bundle = MeasureAgent().gather_evidence("Explain Does Not Exist", context)

    assert bundle.status == AIAnswerStatus.INSUFFICIENT_EVIDENCE
    assert bundle.can_answer is False


def test_measure_agent_conflicting_evidence_when_tmdl_and_xmla_disagree():
    xmla_metadata = XmlaSemanticModelMetadataResponse(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        xmla_endpoint="powerbi://api.powerbi.com/v1.0/myorg/Sales",
        table_count=1,
        column_count=2,
        measure_count=3,
        relationship_count=0,
        hierarchy_count=0,
        partition_count=1,
        tables=[
            XmlaSemanticModelTable(
                name="Sales",
                measures=[
                    XmlaSemanticModelMeasure(
                        name="Gross Margin %",
                        expression="DIVIDE([Net Sales], [Gross Profit])",
                    ),
                ],
            )
        ],
    )
    context = _resolved_measure_context(xmla_metadata=xmla_metadata)

    bundle = MeasureAgent().gather_evidence("Explain Gross Margin %", context)

    assert bundle.status == AIAnswerStatus.CONFLICTING_EVIDENCE
    assert bundle.can_answer is False
    assert len(bundle.conflicts) == 1
    assert bundle.conflicts[0].definition_value == GROSS_MARGIN_DAX
    assert bundle.conflicts[0].runtime_value == "DIVIDE([Net Sales], [Gross Profit])"


def test_measure_agent_no_conflict_when_xmla_matches_tmdl():
    xmla_metadata = XmlaSemanticModelMetadataResponse(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        xmla_endpoint="powerbi://api.powerbi.com/v1.0/myorg/Sales",
        table_count=1,
        column_count=2,
        measure_count=3,
        relationship_count=0,
        hierarchy_count=0,
        partition_count=1,
        tables=[
            XmlaSemanticModelTable(
                name="Sales",
                measures=[
                    XmlaSemanticModelMeasure(
                        name="Gross Margin %",
                        expression=GROSS_MARGIN_DAX,
                    ),
                ],
            )
        ],
    )
    context = _resolved_measure_context(xmla_metadata=xmla_metadata)

    bundle = MeasureAgent().gather_evidence("Explain Gross Margin %", context)

    assert bundle.status == AIAnswerStatus.ANSWERED
    assert bundle.conflicts == []
