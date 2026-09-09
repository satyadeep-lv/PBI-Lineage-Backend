import asyncio
from collections import Counter

import pytest

from app.schemas.explorer import ExplorerRequest
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
    NormalizedReportPage,
    NormalizedReportVisual,
    NormalizedVisualPosition,
    SemanticModelReference,
    VisualFieldReference,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.report import Report
from app.schemas.workspace import Workspace
from app.services.explorer_service import (
    REPORT_LAYOUT,
    SEMANTIC_MODEL_OBJECTS,
    ExplorerService,
)

WORKSPACE_ID = "f089354e-8366-4e18-aea3-4cb4a3a50b48"
REPORT_IDS = (
    "879445d6-3a9e-4a74-b5ae-7c0ddabf0f11",
    "430bb875-3db2-4b76-a246-feb8bb542ca3",
)
MODEL_ID = "cfafbeb1-8037-4d0c-896e-a46fb27ff229"


class _ConcurrencyProbe:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0

    async def pause(self) -> None:
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1


class _WorkspaceService:
    def __init__(self, calls: Counter, probe: _ConcurrencyProbe) -> None:
        self.calls = calls
        self.probe = probe

    async def get_workspace(self, *, workspace_id: str, access_token: str):
        self.calls["workspace"] += 1
        await self.probe.pause()
        return Workspace(id=workspace_id, name="Sales Workspace")


class _ReportService:
    def __init__(self, calls: Counter, probe: _ConcurrencyProbe) -> None:
        self.calls = calls
        self.probe = probe

    async def get_report(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
    ):
        self.calls["report"] += 1
        await self.probe.pause()
        return Report(
            id=report_id,
            name=f"Sales Report {report_id[-1]}",
            dataset_id=MODEL_ID,
        )


class _ReportDefinitionService:
    def __init__(self, calls: Counter, probe: _ConcurrencyProbe) -> None:
        self.calls = calls
        self.probe = probe

    async def get_normalized_definition(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
        definition_format: str,
    ):
        self.calls["report_definition"] += 1
        await self.probe.pause()
        return _report_definition(workspace_id, report_id)


class _SemanticModelDefinitionService:
    def __init__(self, calls: Counter, probe: _ConcurrencyProbe) -> None:
        self.calls = calls
        self.probe = probe

    async def get_parsed_definition(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        definition_format: str,
    ):
        self.calls["semantic_model_definition"] += 1
        await self.probe.pause()
        return _semantic_model(workspace_id, semantic_model_id)


class _GatewayService:
    async def list_gateways(self, *, access_token: str):
        raise AssertionError("Gateway calls must remain opt-in.")


@pytest.mark.asyncio
async def test_snapshot_deduplicates_provider_calls_and_builds_all_datasets():
    calls: Counter = Counter()
    probe = _ConcurrencyProbe()
    service = ExplorerService(
        workspace_service=_WorkspaceService(calls, probe),
        report_service=_ReportService(calls, probe),
        report_definition_service=_ReportDefinitionService(calls, probe),
        semantic_model_definition_service=_SemanticModelDefinitionService(
            calls,
            probe,
        ),
        gateway_service=_GatewayService(),
        max_concurrency=2,
    )
    request = ExplorerRequest.model_validate(
        {
            "reports": [
                {
                    "workspace_id": WORKSPACE_ID,
                    "report_id": report_id,
                }
                for report_id in REPORT_IDS
            ]
        }
    )

    snapshot = await service.build_snapshot(
        request,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
    )

    assert calls == {
        "workspace": 1,
        "report": 2,
        "report_definition": 2,
        "semantic_model_definition": 1,
    }
    assert probe.maximum == 2
    assert snapshot.report_count == 2
    assert snapshot.semantic_model_count == 1
    assert snapshot.source_database_lineage.count == 2
    assert snapshot.semantic_model_objects.count == 12
    assert snapshot.measure_source_lineage.count == 6
    assert snapshot.report_layout.count == 2
    assert snapshot.visual_source_lookup.count == 2

    source_row = snapshot.source_database_lineage.rows[0]
    assert source_row.semantic_table == "Sales"
    assert source_row.source_provider == "snowflake"
    assert source_row.source_fully_qualified_name == "ANALYTICS.MART.FACT_SALES"

    margin_rows = [
        row
        for row in snapshot.measure_source_lineage.rows
        if row.semantic_object_name == "Margin"
    ]
    assert {row.dependency_depth for row in margin_rows} == {2}
    assert {row.source_column_name for row in margin_rows} == {"Amount"}

    layout_row = snapshot.report_layout.rows[0]
    assert layout_row.page_name == "Executive Summary"
    assert layout_row.visual_name == "Revenue by region"
    assert layout_row.column_measure_name == "Revenue"

    lookup_row = snapshot.visual_source_lookup.rows[0]
    assert lookup_row.match_status == "matched"
    assert lookup_row.semantic_object_type == "measure"
    assert lookup_row.semantic_object_name == "Revenue"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dataset", "expected_calls"),
    [
        (
            REPORT_LAYOUT,
            {
                "workspace": 1,
                "report": 1,
                "report_definition": 1,
            },
        ),
        (
            SEMANTIC_MODEL_OBJECTS,
            {
                "workspace": 1,
                "report": 1,
                "semantic_model_definition": 1,
            },
        ),
    ],
)
async def test_focused_dataset_skips_unneeded_definition_calls(
    dataset,
    expected_calls,
):
    calls: Counter = Counter()
    probe = _ConcurrencyProbe()
    service = ExplorerService(
        workspace_service=_WorkspaceService(calls, probe),
        report_service=_ReportService(calls, probe),
        report_definition_service=_ReportDefinitionService(calls, probe),
        semantic_model_definition_service=_SemanticModelDefinitionService(
            calls,
            probe,
        ),
        gateway_service=_GatewayService(),
    )
    request = ExplorerRequest.model_validate(
        {
            "reports": [
                {
                    "workspace_id": WORKSPACE_ID,
                    "report_id": REPORT_IDS[0],
                }
            ]
        }
    )

    await service.build_snapshot(
        request,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
        datasets=frozenset({dataset}),
    )

    assert calls == expected_calls


def _report_definition(
    workspace_id: str,
    report_id: str,
) -> NormalizedReportDefinitionResponse:
    return NormalizedReportDefinitionResponse(
        workspace_id=workspace_id,
        report_id=report_id,
        format="PBIR",
        semantic_model=SemanticModelReference(
            mode="by_connection",
            semantic_model_id=MODEL_ID,
        ),
        pages=[
            NormalizedReportPage(
                name="ReportSection",
                display_name="Executive Summary",
                order=0,
                visuals=[
                    NormalizedReportVisual(
                        id="visual-1",
                        internal_name="visual-1",
                        title="Revenue by region",
                        visual_type="columnChart",
                        has_query=True,
                        position=NormalizedVisualPosition(
                            x=8,
                            y=120,
                            width=571,
                            height=264,
                        ),
                        field_references=[
                            VisualFieldReference(
                                object_type="measure",
                                table_name="Sales",
                                object_name="Revenue",
                                usage="projection",
                                role="Y",
                                query_ref="Sales.Revenue",
                            )
                        ],
                    )
                ],
                visual_count=1,
            )
        ],
        page_count=1,
        visual_count=1,
        source_part_count=4,
        decoded_json_part_count=4,
        warnings=[],
    )


def _semantic_model(
    workspace_id: str,
    semantic_model_id: str,
) -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id=workspace_id,
        semantic_model_id=semantic_model_id,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                columns=[
                    ParsedSemanticModelColumn(
                        name="Amount",
                        data_type="decimal",
                        source_column="AMOUNT",
                    ),
                    ParsedSemanticModelColumn(
                        name="Region",
                        data_type="string",
                        source_column="REGION",
                    ),
                    ParsedSemanticModelColumn(
                        name="Band",
                        data_type="string",
                        expression='IF(\'Sales\'[Amount] > 100, "High", "Low")',
                    ),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Revenue",
                        expression="SUM('Sales'[Amount])",
                    ),
                    ParsedSemanticModelMeasure(
                        name="Margin",
                        expression="[Revenue] * 0.2",
                    ),
                ],
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Sales",
                        source_type="m",
                        expression=(
                            "Snowflake.Databases("
                            '"acme.snowflakecomputing.com", "ANALYTICS", '
                            '[Warehouse="WH"]){[Schema="MART",'
                            'Item="FACT_SALES"]}[Data]'
                        ),
                    )
                ],
            )
        ],
    )
