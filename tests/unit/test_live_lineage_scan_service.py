from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import InsufficientPermissionsError
from app.schemas.gateway import (
    Gateway,
    GatewayDatasource,
    GatewayDatasourceListResponse,
    GatewayListResponse,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.report_semantic_lineage import ReportSemanticLineageResponse
from app.schemas.scan_job import LiveLineageScanRequest
from app.services.live_lineage_scan_service import LiveLineageScanService


def _semantic_model() -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                columns=[ParsedSemanticModelColumn(name="Amount")],
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


@pytest.mark.asyncio
async def test_live_scan_builds_graph_and_matches_gateway_metadata():
    service = LiveLineageScanService()
    service.semantic_model_service.get_parsed_definition = AsyncMock(
        return_value=_semantic_model()
    )
    service.gateway_service.list_gateways = AsyncMock(
        return_value=GatewayListResponse(
            gateways=[Gateway(id="gateway-1", name="Gateway", type="Resource")],
            count=1,
        )
    )
    service.gateway_service.list_datasources = AsyncMock(
        return_value=GatewayDatasourceListResponse(
            gateway_id="gateway-1",
            datasources=[
                GatewayDatasource(
                    id="datasource-1",
                    gateway_id="gateway-1",
                    datasource_type="Sql",
                    connection_details=(
                        '{"server":"sql.example.com","database":"warehouse"}'
                    ),
                )
            ],
            count=1,
        )
    )

    graph = await service.build_graph(
        LiveLineageScanRequest(
            semantic_model_workspace_id="workspace-1",
            semantic_model_id="model-1",
        ),
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
    )

    source = next(
        node
        for node in graph.nodes
        if node.node_type == "physical_source"
        and node.properties.get("provider") == "sqlserver"
    )
    assert source.properties["gateway_id"] == "gateway-1"
    service.semantic_model_service.get_parsed_definition.assert_awaited_once_with(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        access_token="fabric-token",
        definition_format="TMDL",
    )
    service.gateway_service.list_gateways.assert_awaited_once_with(
        access_token="powerbi-token"
    )


@pytest.mark.asyncio
async def test_live_scan_continues_when_gateway_metadata_is_forbidden():
    service = LiveLineageScanService()
    service.semantic_model_service.get_parsed_definition = AsyncMock(
        return_value=_semantic_model()
    )
    service.gateway_service.list_gateways = AsyncMock(
        side_effect=InsufficientPermissionsError("powerbi")
    )

    graph = await service.build_graph(
        LiveLineageScanRequest(
            semantic_model_workspace_id="workspace-1",
            semantic_model_id="model-1",
        ),
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
    )

    assert any(
        "Gateway metadata could not be included" in item for item in graph.warnings
    )
    assert any(node.node_type == "physical_source" for node in graph.nodes)


@pytest.mark.asyncio
async def test_live_scan_optionally_retrieves_and_matches_report_definition():
    service = LiveLineageScanService()
    semantic_model = _semantic_model()
    normalized_report = object()
    report_lineage = ReportSemanticLineageResponse(
        workspace_id="report-workspace",
        report_id="report-1",
        semantic_model_workspace_id="workspace-1",
        semantic_model_id="model-1",
        total_field_reference_count=0,
        matched_field_reference_count=0,
        unmatched_field_reference_count=0,
    )
    service.semantic_model_service.get_parsed_definition = AsyncMock(
        return_value=semantic_model
    )
    service.report_definition_service.get_normalized_definition = AsyncMock(
        return_value=normalized_report
    )
    service.report_lineage_service.match = Mock(return_value=report_lineage)

    graph = await service.build_graph(
        LiveLineageScanRequest(
            semantic_model_workspace_id="workspace-1",
            semantic_model_id="model-1",
            report_workspace_id="report-workspace",
            report_id="report-1",
            include_gateway_sources=False,
        ),
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
    )

    assert graph.report_id == "report-1"
    assert any(node.node_type == "report" for node in graph.nodes)
    service.report_definition_service.get_normalized_definition.assert_awaited_once_with(
        workspace_id="report-workspace",
        report_id="report-1",
        access_token="fabric-token",
        definition_format="PBIR",
    )
    service.report_lineage_service.match.assert_called_once_with(
        report=normalized_report,
        semantic_model=semantic_model,
        semantic_model_workspace_id="workspace-1",
    )
