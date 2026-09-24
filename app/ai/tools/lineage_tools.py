from datetime import UTC, datetime
from typing import Literal

from app.ai.context.resolver import build_lineage_graph
from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import VerificationStatus
from app.ai.models.evidence import EvidenceFactType, EvidenceItem
from app.schemas.lineage_graph import LineageGraph
from app.services.lineage_search_service import LineageNavigationService
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.report_semantic_lineage_service import ReportSemanticLineageService

_DEFAULT_NAVIGATION_DEPTH = 8

_PHYSICAL_NODE_TYPES = frozenset({"physical_source", "snowflake_object"})


def _fact_type_for(
    node_type: str,
    default: EvidenceFactType,
) -> EvidenceFactType:
    if node_type in _PHYSICAL_NODE_TYPES:
        return "source"
    return default


_NODE_TYPE_BY_RESOLVED_OBJECT_TYPE: dict[str, str] = {
    "measure": "semantic_measure",
    "column": "semantic_column",
    "calculated_column": "semantic_column",
    "table": "semantic_table",
}


def build_context_graph(context: ResolvedAIContext) -> LineageGraph | None:
    """Build the one lineage graph a request's evidence is drawn from.

    Report lineage (visual/measure matching) is included whenever both a
    report definition and the semantic model are already resolved, so
    upstream/downstream traversal can reach report/visual nodes too. Best
    effort: matching failures degrade to a semantic-model-only graph rather
    than failing the whole request.
    """
    if context.parsed_semantic_model is None:
        return None

    report_lineage = None
    if context.report_definition is not None and context.workspace_id:
        try:
            report_lineage = ReportSemanticLineageService().match(
                report=context.report_definition,
                semantic_model=context.parsed_semantic_model,
                semantic_model_workspace_id=context.workspace_id,
            )
        except Exception:  # noqa: BLE001 - heuristic matcher, degrade not crash
            report_lineage = None

    return build_lineage_graph(
        context.parsed_semantic_model,
        report_lineage=report_lineage,
    )


def find_object_node_id(
    graph: LineageGraph,
    resolved_object: ResolvedObject,
) -> str | None:
    node_type = _NODE_TYPE_BY_RESOLVED_OBJECT_TYPE.get(resolved_object.object_type)

    for node in graph.nodes:
        if (
            node.node_type == node_type
            and node.qualified_name.casefold()
            == resolved_object.qualified_name.casefold()
        ):
            return node.node_id

    return None


def _navigation_evidence(
    context: ResolvedAIContext,
    *,
    direction: Literal["upstream", "downstream"],
    fact_type: EvidenceFactType,
) -> list[EvidenceItem]:
    if context.resolved_object is None:
        return []

    graph = build_context_graph(context)

    if graph is None:
        return []

    node_id = find_object_node_id(graph, context.resolved_object)

    if node_id is None:
        return []

    navigation = LineageNavigationService().navigate(
        graph,
        node_id=node_id,
        direction=direction,
        depth=_DEFAULT_NAVIGATION_DEPTH,
        include_non_lineage=False,
    )

    now = datetime.now(UTC)
    items: list[EvidenceItem] = []

    for node in navigation.graph.nodes:
        if node.node_id == node_id:
            continue

        items.append(
            EvidenceItem(
                evidence_id="",
                object_type=node.node_type,
                object_id=node.node_id,
                object_name=node.name,
                # A database table is a different kind of answer from a
                # measure or column, so it gets its own section rather than
                # being flattened into one "depends on" list.
                fact_type=_fact_type_for(node.node_type, fact_type),
                source_type="lineage_graph",
                value={
                    "qualified_name": node.qualified_name,
                    "node_type": node.node_type,
                    **({"properties": node.properties} if node.properties else {}),
                },
                workspace_id=context.workspace_id,
                semantic_model_id=context.semantic_model_id,
                verification_status=VerificationStatus.VERIFIED,
                retrieved_at=now,
                source_reference=f"graph_node:{node.node_id}",
            )
        )

    return items


def get_upstream_lineage(context: ResolvedAIContext) -> list[EvidenceItem]:
    """What the resolved object depends on (bounded-depth upstream)."""
    return _navigation_evidence(
        context,
        direction="upstream",
        fact_type="dependency",
    )


def get_downstream_lineage(context: ResolvedAIContext) -> list[EvidenceItem]:
    """What depends on the resolved object (bounded-depth downstream)."""
    return _navigation_evidence(
        context,
        direction="downstream",
        fact_type="usage",
    )


def get_semantic_model_details(context: ResolvedAIContext) -> list[EvidenceItem]:
    model = context.parsed_semantic_model

    if model is None:
        return []

    table_count = len(model.tables)
    measure_count = sum(len(table.measures) for table in model.tables)
    column_count = sum(len(table.columns) for table in model.tables)

    return [
        EvidenceItem(
            evidence_id="",
            object_type="semantic_model",
            object_id=model.semantic_model_id,
            object_name="This semantic model",
            fact_type="definition",
            source_type="tmdl",
            value={
                "table_count": table_count,
                "measure_count": measure_count,
                "column_count": column_count,
                "table_names": [table.name for table in model.tables],
                # Names, not just counts: "what measures are there" is a
                # question the model can answer outright, and returning only
                # a count made it look unanswerable.
                "measures_by_table": {
                    table.name: [measure.name for measure in table.measures]
                    for table in model.tables
                    if table.measures
                },
            },
            workspace_id=model.workspace_id,
            semantic_model_id=model.semantic_model_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=datetime.now(UTC),
            source_reference=f"semantic_model:{model.semantic_model_id}",
        )
    ]


def get_physical_sources(context: ResolvedAIContext) -> list[EvidenceItem]:
    model = context.parsed_semantic_model

    if model is None:
        return []

    discovery = PhysicalSourceDiscoveryService().discover(model)
    now = datetime.now(UTC)

    return [
        EvidenceItem(
            evidence_id="",
            object_type="physical_source",
            object_id=source.source_id,
            object_name=(
                source.object_name
                or source.database
                or source.path
                or source.url
                or source.provider
            ),
            fact_type="source",
            source_type="tmdl",
            value=source.model_dump(exclude_none=True),
            workspace_id=model.workspace_id,
            semantic_model_id=model.semantic_model_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=now,
            source_reference=f"physical_source:{source.source_id}",
        )
        for source in discovery.sources
    ]
