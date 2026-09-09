import pytest

from app.schemas.dax_dependency import DaxDependencyAnalysisResponse
from app.schemas.lineage_graph import LineageGraphBuildRequest
from app.schemas.normalized_report_definition import VisualFieldReference
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.report_semantic_lineage import (
    ReportSemanticLineageResponse,
    SemanticLineageFieldMatch,
    SemanticLineageObject,
)
from app.services.impact_analysis_service import ImpactAnalysisService
from app.services.lineage_graph_service import LineageGraphService


def _build_request() -> LineageGraphBuildRequest:
    semantic_model = ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                columns=[ParsedSemanticModelColumn(name="Amount")],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Total Sales",
                        expression="SUM(Sales[Amount])",
                    )
                ],
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Sales",
                        source_type="m",
                        expression=('Sql.Database("sql.example.com", "warehouse")'),
                    )
                ],
            )
        ],
    )
    report_lineage = ReportSemanticLineageResponse(
        workspace_id="workspace-1",
        report_id="report-1",
        semantic_model_workspace_id="workspace-1",
        semantic_model_id="model-1",
        total_field_reference_count=1,
        matched_field_reference_count=1,
        unmatched_field_reference_count=0,
        field_matches=[
            SemanticLineageFieldMatch(
                page_name="ReportSection",
                page_display_name="Overview",
                visual_id="visual-1",
                visual_title="Revenue",
                field_reference=VisualFieldReference(
                    object_type="measure",
                    table_name="Sales",
                    object_name="Total Sales",
                    usage="projection",
                ),
                status="matched",
                semantic_object=SemanticLineageObject(
                    object_type="measure",
                    table_name="Sales",
                    object_name="Total Sales",
                ),
                match_confidence=1.0,
            )
        ],
    )
    return LineageGraphBuildRequest(
        semantic_model=semantic_model,
        report_lineage=report_lineage,
    )


def test_builds_canonical_end_to_end_graph():
    graph = LineageGraphService().build(_build_request())

    assert graph.node_count == len(graph.nodes)
    assert graph.edge_count == len(graph.edges)
    assert {edge.edge_type for edge in graph.edges} >= {
        "reads_from",
        "populates",
        "provides_data_to",
        "dax_dependency",
        "used_by_visual",
    }

    source = next(node for node in graph.nodes if node.node_type == "physical_source")
    visual = next(node for node in graph.nodes if node.node_type == "visual")
    impact = ImpactAnalysisService().analyze(graph, node_id=source.node_id)
    visual_impact = next(
        item for item in impact.impacted_nodes if item.node.node_id == visual.node_id
    )

    assert visual_impact.distance == 5
    assert visual_impact.path_node_ids[0] == source.node_id
    assert visual_impact.path_node_ids[-1] == visual.node_id


def test_impact_ignores_containment_edges_by_default():
    graph = LineageGraphService().build(_build_request())
    report = next(node for node in graph.nodes if node.node_type == "report")

    impact = ImpactAnalysisService().analyze(graph, node_id=report.node_id)

    assert impact.impacted_count == 0


def test_impact_reports_depth_truncation():
    graph = LineageGraphService().build(_build_request())
    source = next(node for node in graph.nodes if node.node_type == "physical_source")

    impact = ImpactAnalysisService().analyze(
        graph,
        node_id=source.node_id,
        max_depth=2,
    )

    assert impact.truncated is True
    assert max(item.distance for item in impact.impacted_nodes) == 2


def test_graph_rejects_mismatched_analysis_identity():
    request = _build_request()
    request.dax_analysis = DaxDependencyAnalysisResponse(
        workspace_id="different-workspace",
        semantic_model_id="model-1",
    )

    with pytest.raises(ValueError, match="DAX analysis"):
        LineageGraphService().build(request)
