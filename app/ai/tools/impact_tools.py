from datetime import UTC, datetime

from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import VerificationStatus
from app.ai.models.evidence import EvidenceItem
from app.ai.tools.lineage_tools import build_context_graph, find_object_node_id
from app.services.impact_analysis_service import ImpactAnalysisService

_DEFAULT_IMPACT_DEPTH = 8


def analyze_impact(context: ResolvedAIContext) -> list[EvidenceItem]:
    """Downstream impact of the resolved object, via the real impact graph.

    No LLM inference for impact edges: every item here comes directly from
    ImpactAnalysisService's BFS over lineage-only edges.
    """
    if context.resolved_object is None:
        return []

    graph = build_context_graph(context)

    if graph is None:
        return []

    node_id = find_object_node_id(graph, context.resolved_object)

    if node_id is None:
        return []

    try:
        result = ImpactAnalysisService().analyze(
            graph,
            node_id=node_id,
            max_depth=_DEFAULT_IMPACT_DEPTH,
        )
    except (KeyError, ValueError):
        return []

    now = datetime.now(UTC)

    return [
        EvidenceItem(
            evidence_id="",
            object_type=impacted.node.node_type,
            object_id=impacted.node.node_id,
            object_name=impacted.node.name,
            fact_type="impact",
            source_type="lineage_graph",
            value={
                "qualified_name": impacted.node.qualified_name,
                "node_type": impacted.node.node_type,
                "distance": impacted.distance,
            },
            workspace_id=context.workspace_id,
            semantic_model_id=context.semantic_model_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=now,
            source_reference=f"graph_node:{impacted.node.node_id}",
        )
        for impacted in result.impacted_nodes
    ]
