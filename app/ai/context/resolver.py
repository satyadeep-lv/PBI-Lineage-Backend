from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.requests import AIChatContext
from app.core.exceptions import AppException
from app.schemas.lineage_graph import (
    LineageGraph,
    LineageGraphBuildRequest,
    LineageNodeType,
)
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.report_semantic_lineage import ReportSemanticLineageResponse
from app.services.lineage_graph_service import LineageGraphService
from app.services.lineage_search_service import LineageSearchService
from app.services.report_definition_service import ReportDefinitionService
from app.services.report_service import ReportService
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.workspace_service import WorkspaceService

_NODE_TYPES_BY_OBJECT_TYPE: dict[str, list[LineageNodeType]] = {
    "measure": ["semantic_measure"],
    "calculated_column": ["semantic_column"],
    "column": ["semantic_column"],
    "table": ["semantic_table"],
}
_DEFAULT_OBJECT_NODE_TYPES: list[LineageNodeType] = [
    "semantic_measure",
    "semantic_column",
]
_RESOLVED_OBJECT_TYPE_BY_NODE_TYPE = {
    "semantic_measure": "measure",
    "semantic_table": "table",
}


def build_lineage_graph(
    parsed_semantic_model: ParsedSemanticModelResponse,
    *,
    report_lineage: ReportSemanticLineageResponse | None = None,
) -> LineageGraph:
    """Single, shared entry point for turning fetched evidence into a graph.

    Reused by the context resolver (object resolution) and every lineage/
    impact tool, so the graph algorithm itself is never duplicated.
    """
    return LineageGraphService().build(
        LineageGraphBuildRequest(
            semantic_model=parsed_semantic_model,
            report_lineage=report_lineage,
        )
    )


class AIContextResolver:
    """Validates and resolves AI request context against real access.

    Each step only proceeds once the prior one succeeded, mirroring:
    workspace access -> report belongs to workspace -> semantic model
    belongs to workspace -> resolve named object. A failure at any step
    collapses to the same "could not verify" note regardless of whether the
    underlying cause was 401/403/404, so a caller can never distinguish
    "exists but you can't see it" from "does not exist".
    """

    def __init__(
        self,
        *,
        powerbi_access_token: str | None,
        fabric_access_token: str | None,
    ) -> None:
        self._powerbi_access_token = powerbi_access_token
        self._fabric_access_token = fabric_access_token

    async def resolve(
        self,
        context: AIChatContext | None,
    ) -> ResolvedAIContext:
        resolved = ResolvedAIContext()

        if context is None:
            return resolved

        if context.workspace_id:
            await self._resolve_workspace(resolved, context.workspace_id)

        if resolved.workspace_id and context.report_id:
            await self._resolve_report(resolved, context.report_id)

        if resolved.workspace_id and context.semantic_model_id:
            await self._resolve_semantic_model(resolved, context.semantic_model_id)

        if resolved.parsed_semantic_model and (
            context.object_name or context.object_id
        ):
            await self._resolve_object(resolved, context)

        return resolved

    async def _resolve_workspace(
        self,
        resolved: ResolvedAIContext,
        workspace_id: str,
    ) -> None:
        if not self._powerbi_access_token:
            resolved.resolution_notes.append(
                "No Power BI session is available to verify workspace access."
            )
            return

        try:
            await WorkspaceService().get_workspace(
                workspace_id=workspace_id,
                access_token=self._powerbi_access_token,
            )
        except AppException:
            resolved.resolution_notes.append(
                "The requested workspace could not be verified against the "
                "authenticated session."
            )
            return

        resolved.workspace_id = workspace_id

    async def _resolve_report(
        self,
        resolved: ResolvedAIContext,
        report_id: str,
    ) -> None:
        if not self._powerbi_access_token:
            resolved.resolution_notes.append(
                "No Power BI session is available to verify report access."
            )
            return

        try:
            await ReportService().get_report(
                workspace_id=resolved.workspace_id,
                report_id=report_id,
                access_token=self._powerbi_access_token,
            )
        except AppException:
            resolved.resolution_notes.append(
                "The requested report could not be verified within the "
                "authorized workspace."
            )
            return

        resolved.report_id = report_id

        if not self._fabric_access_token:
            resolved.resolution_notes.append(
                "No Fabric session is available to retrieve the report definition."
            )
            return

        try:
            resolved.report_definition = (
                await ReportDefinitionService().get_normalized_definition(
                    workspace_id=resolved.workspace_id,
                    report_id=report_id,
                    access_token=self._fabric_access_token,
                )
            )
        except AppException:
            resolved.resolution_notes.append(
                "The report definition could not be retrieved."
            )

    async def _resolve_semantic_model(
        self,
        resolved: ResolvedAIContext,
        semantic_model_id: str,
    ) -> None:
        if not self._fabric_access_token:
            resolved.resolution_notes.append(
                "No Fabric session is available to verify the semantic model."
            )
            return

        try:
            resolved.parsed_semantic_model = (
                await SemanticModelDefinitionService().get_parsed_definition(
                    workspace_id=resolved.workspace_id,
                    semantic_model_id=semantic_model_id,
                    access_token=self._fabric_access_token,
                )
            )
        except AppException:
            resolved.resolution_notes.append(
                "The requested semantic model could not be verified within "
                "the authorized workspace."
            )
            return

        resolved.semantic_model_id = semantic_model_id

    async def _resolve_object(
        self,
        resolved: ResolvedAIContext,
        context: AIChatContext,
    ) -> None:
        query = context.object_name or context.object_id

        if not query or resolved.parsed_semantic_model is None:
            return

        graph = build_lineage_graph(resolved.parsed_semantic_model)
        node_types = _NODE_TYPES_BY_OBJECT_TYPE.get(
            context.object_type or "",
            _DEFAULT_OBJECT_NODE_TYPES,
        )

        result = LineageSearchService().search(
            graph,
            query=query,
            node_types=node_types,
            semantic_model_id=resolved.semantic_model_id,
            limit=5,
        )

        if not result.results:
            resolved.resolution_notes.append(
                f"No object named '{query}' was found in the resolved semantic model."
            )
            return

        top_score = result.results[0].score
        top_matches = [item for item in result.results if item.score == top_score]

        if len(top_matches) > 1:
            resolved.resolution_notes.append(
                f"'{query}' matched more than one object: "
                + ", ".join(item.node.qualified_name for item in top_matches)
            )
            return

        node = top_matches[0].node
        table_name = str(
            node.properties.get("table_name")
            or (node.name if node.node_type == "semantic_table" else "")
        )
        object_type = _RESOLVED_OBJECT_TYPE_BY_NODE_TYPE.get(node.node_type)

        if object_type is None and node.node_type == "semantic_column":
            object_type = (
                "calculated_column"
                if node.properties.get("is_calculated")
                else "column"
            )

        if object_type is None:
            resolved.resolution_notes.append(
                f"'{query}' resolved to an unsupported object type ({node.node_type})."
            )
            return

        resolved.resolved_object = ResolvedObject(
            object_type=object_type,
            table_name=table_name,
            object_name=node.name,
            qualified_name=node.qualified_name,
        )
