import asyncio
from datetime import UTC, datetime

from app.core.exceptions import AppException
from app.domain.lineage_ids import stable_lineage_id
from app.schemas.estate import (
    EstateDiscoveryResponse,
    EstateDiscoveryWarning,
    EstateReportBinding,
    EstateWorkspaceInventory,
)
from app.schemas.lineage_graph import LineageEdge, LineageGraph, LineageNode
from app.schemas.report import ReportListResponse
from app.schemas.semantic_model import SemanticModelListResponse
from app.services.report_service import ReportService
from app.services.semantic_model_service import SemanticModelService
from app.services.workspace_service import WorkspaceService


class EstateDiscoveryService:
    def __init__(self) -> None:
        self.workspace_service = WorkspaceService()
        self.report_service = ReportService()
        self.semantic_model_service = SemanticModelService()

    async def discover(
        self,
        *,
        access_token: str,
        top: int = 5000,
        skip: int = 0,
    ) -> EstateDiscoveryResponse:
        workspace_response = await self.workspace_service.list_workspaces(
            access_token=access_token,
            top=top,
            skip=skip,
        )
        inventories: list[EstateWorkspaceInventory] = []
        warnings: list[EstateDiscoveryWarning] = []

        for workspace in workspace_response.workspaces:
            reports, semantic_models = await asyncio.gather(
                self._reports(
                    workspace.id,
                    access_token,
                    warnings,
                ),
                self._semantic_models(
                    workspace.id,
                    access_token,
                    warnings,
                ),
            )
            model_ids = {model.id for model in semantic_models.semantic_models}
            bindings = [
                EstateReportBinding(
                    report_id=report.id,
                    semantic_model_id=report.dataset_id,
                    status=(
                        "matched" if report.dataset_id in model_ids else "unresolved"
                    ),
                )
                for report in reports.reports
            ]
            inventories.append(
                EstateWorkspaceInventory(
                    workspace=workspace,
                    reports=reports.reports,
                    semantic_models=semantic_models.semantic_models,
                    report_bindings=bindings,
                )
            )

        graph = self._build_graph(inventories)
        return EstateDiscoveryResponse(
            workspaces=inventories,
            graph=graph,
            warnings=warnings,
            workspace_count=len(inventories),
            report_count=sum(len(item.reports) for item in inventories),
            semantic_model_count=sum(len(item.semantic_models) for item in inventories),
        )

    async def _reports(
        self,
        workspace_id: str,
        access_token: str,
        warnings: list[EstateDiscoveryWarning],
    ) -> ReportListResponse:
        try:
            return await self.report_service.list_reports(
                workspace_id=workspace_id,
                access_token=access_token,
            )
        except AppException as exc:
            warnings.append(
                EstateDiscoveryWarning(
                    code=exc.code,
                    message=exc.message,
                    workspace_id=workspace_id,
                    resource_type="reports",
                )
            )
            return ReportListResponse(
                workspace_id=workspace_id,
                reports=[],
                count=0,
            )

    async def _semantic_models(
        self,
        workspace_id: str,
        access_token: str,
        warnings: list[EstateDiscoveryWarning],
    ) -> SemanticModelListResponse:
        try:
            return await self.semantic_model_service.list_semantic_models(
                workspace_id=workspace_id,
                access_token=access_token,
            )
        except AppException as exc:
            warnings.append(
                EstateDiscoveryWarning(
                    code=exc.code,
                    message=exc.message,
                    workspace_id=workspace_id,
                    resource_type="semantic_models",
                )
            )
            return SemanticModelListResponse(
                workspace_id=workspace_id,
                semantic_models=[],
                count=0,
            )

    @staticmethod
    def _build_graph(
        inventories: list[EstateWorkspaceInventory],
    ) -> LineageGraph:
        nodes: dict[str, LineageNode] = {}
        edges: dict[tuple[str, str, str], LineageEdge] = {}

        for inventory in inventories:
            workspace = inventory.workspace
            workspace_node_id = stable_lineage_id("workspace", workspace.id)
            nodes[workspace_node_id] = LineageNode(
                node_id=workspace_node_id,
                node_type="workspace",
                name=workspace.name,
                qualified_name=workspace.name,
                workspace_id=workspace.id,
            )

            for model in inventory.semantic_models:
                model_node_id = stable_lineage_id(
                    "semantic_model",
                    workspace.id,
                    model.id,
                )
                nodes[model_node_id] = LineageNode(
                    node_id=model_node_id,
                    node_type="semantic_model",
                    name=model.name,
                    qualified_name=f"{workspace.name}.{model.name}",
                    workspace_id=workspace.id,
                    semantic_model_id=model.id,
                )
                EstateDiscoveryService._edge(
                    edges,
                    workspace_node_id,
                    model_node_id,
                    "contains",
                    False,
                )

            for report in inventory.reports:
                report_node_id = stable_lineage_id("report", workspace.id, report.id)
                nodes[report_node_id] = LineageNode(
                    node_id=report_node_id,
                    node_type="report",
                    name=report.name,
                    qualified_name=f"{workspace.name}.{report.name}",
                    workspace_id=workspace.id,
                    report_id=report.id,
                    properties={"semantic_model_id": report.dataset_id},
                )
                EstateDiscoveryService._edge(
                    edges,
                    workspace_node_id,
                    report_node_id,
                    "contains",
                    False,
                )
                if report.dataset_id:
                    model_node_id = stable_lineage_id(
                        "semantic_model",
                        workspace.id,
                        report.dataset_id,
                    )
                    if model_node_id in nodes:
                        EstateDiscoveryService._edge(
                            edges,
                            model_node_id,
                            report_node_id,
                            "powers_report",
                            True,
                        )

        ordered_nodes = sorted(nodes.values(), key=lambda node: node.node_id)
        ordered_edges = sorted(edges.values(), key=lambda edge: edge.edge_id)
        return LineageGraph(
            graph_id=stable_lineage_id("graph", "estate"),
            created_at=datetime.now(UTC),
            nodes=ordered_nodes,
            edges=ordered_edges,
            node_count=len(ordered_nodes),
            edge_count=len(ordered_edges),
        )

    @staticmethod
    def _edge(
        edges: dict[tuple[str, str, str], LineageEdge],
        source_id: str,
        target_id: str,
        edge_type: str,
        is_lineage: bool,
    ) -> None:
        key = (source_id, target_id, edge_type)
        edges[key] = LineageEdge(
            edge_id=stable_lineage_id("edge", *key),
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            is_lineage=is_lineage,
        )
