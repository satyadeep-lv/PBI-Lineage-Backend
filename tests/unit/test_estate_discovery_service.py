from unittest.mock import AsyncMock

import pytest

from app.schemas.report import Report, ReportListResponse
from app.schemas.semantic_model import SemanticModel, SemanticModelListResponse
from app.schemas.workspace import Workspace, WorkspaceListResponse
from app.services.estate_discovery_service import EstateDiscoveryService


@pytest.mark.asyncio
async def test_discovers_estate_inventory_and_report_bindings():
    service = EstateDiscoveryService()
    service.workspace_service.list_workspaces = AsyncMock(
        return_value=WorkspaceListResponse(
            workspaces=[Workspace(id="workspace-1", name="Finance")],
            count=1,
            top=100,
            skip=0,
        )
    )
    service.report_service.list_reports = AsyncMock(
        return_value=ReportListResponse(
            workspace_id="workspace-1",
            reports=[
                Report(
                    id="report-1",
                    name="Revenue",
                    dataset_id="model-1",
                )
            ],
            count=1,
        )
    )
    service.semantic_model_service.list_semantic_models = AsyncMock(
        return_value=SemanticModelListResponse(
            workspace_id="workspace-1",
            semantic_models=[SemanticModel(id="model-1", name="Sales")],
            count=1,
        )
    )

    result = await service.discover(
        access_token="fake-token",
        top=100,
    )

    assert result.workspace_count == 1
    assert result.report_count == 1
    assert result.semantic_model_count == 1
    assert result.workspaces[0].report_bindings[0].status == "matched"
    assert any(edge.edge_type == "powers_report" for edge in result.graph.edges)


@pytest.mark.asyncio
async def test_marks_report_with_unknown_model_as_unresolved():
    service = EstateDiscoveryService()
    service.workspace_service.list_workspaces = AsyncMock(
        return_value=WorkspaceListResponse(
            workspaces=[Workspace(id="workspace-1", name="Finance")],
            count=1,
            top=5000,
            skip=0,
        )
    )
    service.report_service.list_reports = AsyncMock(
        return_value=ReportListResponse(
            workspace_id="workspace-1",
            reports=[
                Report(
                    id="report-1",
                    name="Revenue",
                    dataset_id="missing-model",
                )
            ],
            count=1,
        )
    )
    service.semantic_model_service.list_semantic_models = AsyncMock(
        return_value=SemanticModelListResponse(
            workspace_id="workspace-1",
            semantic_models=[],
            count=0,
        )
    )

    result = await service.discover(access_token="fake-token")

    assert result.workspaces[0].report_bindings[0].status == "unresolved"
    assert not any(edge.edge_type == "powers_report" for edge in result.graph.edges)
