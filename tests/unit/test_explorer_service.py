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
from app.services.cross_model_lineage_service import (
    CrossModelDiscoveryResult,
    UpstreamModelRef,
)
from app.services.explorer_service import (
    REPORT_LAYOUT,
    REPORT_SOURCE_TABLES,
    SEMANTIC_MODEL_OBJECTS,
    VISUAL_SOURCE_LOOKUP,
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
    def __init__(
        self,
        calls: Counter,
        probe: _ConcurrencyProbe,
        dataset_workspace_id: str | None = None,
    ) -> None:
        self.calls = calls
        self.probe = probe
        self.dataset_workspace_id = dataset_workspace_id

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
            dataset_workspace_id=self.dataset_workspace_id,
        )


class _ReportDefinitionService:
    def __init__(
        self,
        calls: Counter,
        probe: _ConcurrencyProbe,
        definition_factory=None,
    ) -> None:
        self.calls = calls
        self.probe = probe
        self.definition_factory = definition_factory or _report_definition

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
        return self.definition_factory(workspace_id, report_id)


class _SemanticModelDefinitionService:
    def __init__(
        self,
        calls: Counter,
        probe: _ConcurrencyProbe,
        model_factory=None,
    ) -> None:
        self.calls = calls
        self.probe = probe
        self.model_factory = model_factory or _semantic_model
        self.requested_workspace_ids: list[str] = []

    async def get_parsed_definition(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        definition_format: str,
    ):
        self.requested_workspace_ids.append(workspace_id)
        self.calls["semantic_model_definition"] += 1
        await self.probe.pause()
        return self.model_factory(workspace_id, semantic_model_id)


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
    assert snapshot.report_source_tables.count == 2
    assert snapshot.semantic_model_objects.count == 12
    assert snapshot.measure_source_lineage.count == 6
    assert snapshot.report_layout.count == 2
    assert snapshot.visual_source_lookup.count == 2

    source_row = snapshot.source_database_lineage.rows[0]
    assert source_row.semantic_table == "Sales"
    assert source_row.source_provider == "snowflake"
    assert source_row.source_fully_qualified_name == "ANALYTICS.MART.FACT_SALES"

    table_row = snapshot.report_source_tables.rows[0]
    assert table_row.workspace_name == "Sales Workspace"
    assert table_row.semantic_model_id == MODEL_ID
    assert table_row.source_account == "acme.snowflakecomputing.com"
    assert table_row.source_database == "ANALYTICS"
    assert table_row.source_schema == "MART"
    assert table_row.table_name == "FACT_SALES"
    assert table_row.source_object_type == "table"

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


@pytest.mark.asyncio
async def test_report_source_tables_deduplicates_shared_tables_and_flags_views():
    calls: Counter = Counter()
    probe = _ConcurrencyProbe()
    service = ExplorerService(
        workspace_service=_WorkspaceService(calls, probe),
        report_service=_ReportService(calls, probe),
        report_definition_service=_ReportDefinitionService(calls, probe),
        semantic_model_definition_service=_SemanticModelDefinitionService(
            calls,
            probe,
            model_factory=_semantic_model_with_shared_and_view_sources,
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

    snapshot = await service.build_snapshot(
        request,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
        datasets=frozenset({REPORT_SOURCE_TABLES}),
    )

    # Two semantic tables (Sales, SalesArchive) share one physical table, so
    # they must collapse to a single row instead of one row per semantic
    # table/partition.
    assert snapshot.report_source_tables.count == 2
    rows = {row.table_name: row for row in snapshot.report_source_tables.rows}
    assert rows["FactSales"].source_object_type == "table"
    assert rows["FactSales"].source_database == "Analytics"
    assert rows["FactSales"].source_schema == "dbo"
    assert rows["FactSales"].source_account == "sql.example.com"
    assert rows["VwSalesSummary"].source_object_type == "view"


@pytest.mark.asyncio
async def test_source_database_and_report_source_tables_emit_unknown_placeholder():
    calls: Counter = Counter()
    probe = _ConcurrencyProbe()
    service = ExplorerService(
        workspace_service=_WorkspaceService(calls, probe),
        report_service=_ReportService(calls, probe),
        report_definition_service=_ReportDefinitionService(calls, probe),
        semantic_model_definition_service=_SemanticModelDefinitionService(
            calls,
            probe,
            model_factory=_semantic_model_with_unresolved_source,
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

    snapshot = await service.build_snapshot(
        request,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
        datasets=frozenset({"source_database_lineage", REPORT_SOURCE_TABLES}),
    )

    assert snapshot.source_database_lineage.count == 1
    source_row = snapshot.source_database_lineage.rows[0]
    assert source_row.semantic_table == "EmergencyContacts"
    assert source_row.source_object_type == "unknown"
    assert source_row.source_kind == "unknown"
    assert source_row.source_fully_qualified_name == (
        "Unknown Source (e.g., Local Excel File, Web Data, Dataflow, or "
        "Calculated Table)"
    )

    assert snapshot.report_source_tables.count == 1
    table_row = snapshot.report_source_tables.rows[0]
    assert table_row.source_object_type == "unknown"
    assert table_row.table_name is None
    assert table_row.source_account is None


MODEL_WORKSPACE_ID = "0b1d2e3f-4a5b-6c7d-8e9f-0a1b2c3d4e5f"


@pytest.mark.asyncio
async def test_cross_workspace_report_resolves_model_from_dataset_workspace():
    calls: Counter = Counter()
    probe = _ConcurrencyProbe()
    semantic_model_definition_service = _SemanticModelDefinitionService(calls, probe)
    service = ExplorerService(
        workspace_service=_WorkspaceService(calls, probe),
        report_service=_ReportService(
            calls,
            probe,
            dataset_workspace_id=MODEL_WORKSPACE_ID,
        ),
        report_definition_service=_ReportDefinitionService(calls, probe),
        semantic_model_definition_service=semantic_model_definition_service,
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

    snapshot = await service.build_snapshot(
        request,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
        datasets=frozenset({REPORT_SOURCE_TABLES}),
    )

    # The model lives in another workspace than the report, so the Fabric
    # definition call must target the dataset's workspace, not the report's.
    assert semantic_model_definition_service.requested_workspace_ids == [
        MODEL_WORKSPACE_ID
    ]
    assert snapshot.report_source_tables.count == 1
    assert snapshot.report_source_tables.rows[0].table_name == "FACT_SALES"
    assert snapshot.reports[0].semantic_model_workspace_id == MODEL_WORKSPACE_ID


@pytest.mark.asyncio
async def test_explicit_model_workspace_overrides_report_dataset_workspace():
    calls: Counter = Counter()
    probe = _ConcurrencyProbe()
    semantic_model_definition_service = _SemanticModelDefinitionService(calls, probe)
    service = ExplorerService(
        workspace_service=_WorkspaceService(calls, probe),
        report_service=_ReportService(
            calls,
            probe,
            dataset_workspace_id=MODEL_WORKSPACE_ID,
        ),
        report_definition_service=_ReportDefinitionService(calls, probe),
        semantic_model_definition_service=semantic_model_definition_service,
        gateway_service=_GatewayService(),
    )
    request = ExplorerRequest.model_validate(
        {
            "reports": [
                {
                    "workspace_id": WORKSPACE_ID,
                    "report_id": REPORT_IDS[0],
                    "semantic_model_id": MODEL_ID,
                    "semantic_model_workspace_id": WORKSPACE_ID,
                }
            ]
        }
    )

    await service.build_snapshot(
        request,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
        datasets=frozenset({REPORT_SOURCE_TABLES}),
    )

    assert semantic_model_definition_service.requested_workspace_ids == [WORKSPACE_ID]


UPSTREAM_WORKSPACE_ID = "9d8c7b6a-1111-2222-3333-444455556666"
UPSTREAM_DATASET_ID = "8597cc44-71b2-432b-b2c2-f56e07563599"


class _CrossModelLineageService:
    def __init__(self, result: CrossModelDiscoveryResult) -> None:
        self.result = result
        self.discover_calls = 0

    async def discover(self, **kwargs):
        self.discover_calls += 1
        return self.result


@pytest.mark.asyncio
async def test_visual_source_lookup_redirects_to_upstream_via_lineage_tag():
    calls: Counter = Counter()
    probe = _ConcurrencyProbe()
    upstream_model = ParsedSemanticModelResponse(
        workspace_id=UPSTREAM_WORKSPACE_ID,
        semantic_model_id=UPSTREAM_DATASET_ID,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="EmployeeMaster",
                columns=[
                    ParsedSemanticModelColumn(
                        name="EmployeeId",
                        lineage_tag="tag-employee-id",
                    )
                ],
            )
        ],
    )
    cross_model_service = _CrossModelLineageService(
        CrossModelDiscoveryResult(
            upstream_refs={
                UPSTREAM_DATASET_ID: UpstreamModelRef(
                    workspace_id=UPSTREAM_WORKSPACE_ID,
                    semantic_model_id=UPSTREAM_DATASET_ID,
                    name="NativeQueryReoprt",
                )
            },
            upstream_models={UPSTREAM_DATASET_ID: upstream_model},
            warnings=[],
        )
    )
    service = ExplorerService(
        workspace_service=_WorkspaceService(calls, probe),
        report_service=_ReportService(calls, probe),
        report_definition_service=_ReportDefinitionService(
            calls,
            probe,
            definition_factory=_report_definition_with_employee_id_column,
        ),
        semantic_model_definition_service=_SemanticModelDefinitionService(
            calls,
            probe,
            model_factory=_semantic_model_with_source_lineage_tag,
        ),
        gateway_service=_GatewayService(),
        cross_model_lineage_service=cross_model_service,
    )
    request = ExplorerRequest.model_validate(
        {
            "reports": [
                {
                    "workspace_id": WORKSPACE_ID,
                    "report_id": REPORT_IDS[0],
                }
            ],
            "include_cross_model_matching": True,
        }
    )

    snapshot = await service.build_snapshot(
        request,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
        datasets=frozenset({VISUAL_SOURCE_LOOKUP}),
    )

    assert cross_model_service.discover_calls == 1
    assert snapshot.visual_source_lookup.count == 1
    row = snapshot.visual_source_lookup.rows[0]
    assert row.match_status == "matched"
    assert row.primary_dataset_id == MODEL_ID
    assert row.matched_dataset_id == UPSTREAM_DATASET_ID
    assert row.matched_semantic_model == "NativeQueryReoprt"
    assert row.matched_model_role == "upstream"
    assert row.semantic_table == "EmployeeMaster"
    assert row.match_reason == "Upstream object matched by SourceLineageTag"


@pytest.mark.asyncio
async def test_visual_source_lookup_stays_primary_when_matching_disabled():
    calls: Counter = Counter()
    probe = _ConcurrencyProbe()
    cross_model_service = _CrossModelLineageService(
        CrossModelDiscoveryResult(upstream_refs={}, upstream_models={}, warnings=[])
    )
    service = ExplorerService(
        workspace_service=_WorkspaceService(calls, probe),
        report_service=_ReportService(calls, probe),
        report_definition_service=_ReportDefinitionService(
            calls,
            probe,
            definition_factory=_report_definition_with_employee_id_column,
        ),
        semantic_model_definition_service=_SemanticModelDefinitionService(
            calls,
            probe,
            model_factory=_semantic_model_with_source_lineage_tag,
        ),
        gateway_service=_GatewayService(),
        cross_model_lineage_service=cross_model_service,
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

    snapshot = await service.build_snapshot(
        request,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
        datasets=frozenset({VISUAL_SOURCE_LOOKUP}),
    )

    assert cross_model_service.discover_calls == 0
    row = snapshot.visual_source_lookup.rows[0]
    assert row.matched_model_role == "primary"
    assert row.matched_dataset_id == MODEL_ID
    assert row.semantic_table == "Employees"


def _report_definition_with_employee_id_column(
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
                display_name="Employees",
                order=0,
                visuals=[
                    NormalizedReportVisual(
                        id="visual-1",
                        internal_name="visual-1",
                        title="Employee ID",
                        visual_type="table",
                        has_query=True,
                        position=NormalizedVisualPosition(
                            x=0,
                            y=0,
                            width=100,
                            height=100,
                        ),
                        field_references=[
                            VisualFieldReference(
                                object_type="column",
                                table_name="Employees",
                                object_name="EmployeeId",
                                usage="projection",
                                role="Values",
                                query_ref="Employees.EmployeeId",
                            )
                        ],
                    )
                ],
                visual_count=1,
            )
        ],
        page_count=1,
        visual_count=1,
        source_part_count=1,
        decoded_json_part_count=1,
        warnings=[],
    )


def _semantic_model_with_source_lineage_tag(
    workspace_id: str,
    semantic_model_id: str,
) -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id=workspace_id,
        semantic_model_id=semantic_model_id,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="Employees",
                columns=[
                    ParsedSemanticModelColumn(
                        name="EmployeeId",
                        source_lineage_tag="tag-employee-id",
                    )
                ],
            )
        ],
    )


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


def _semantic_model_with_unresolved_source(
    workspace_id: str,
    semantic_model_id: str,
) -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id=workspace_id,
        semantic_model_id=semantic_model_id,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="EmergencyContacts",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="EmergencyContacts",
                        source_type="m",
                        expression=(
                            'Excel.CurrentWorkbook(){[Name="ContactsTable"]}[Content]'
                        ),
                    )
                ],
            )
        ],
    )


def _semantic_model_with_shared_and_view_sources(
    workspace_id: str,
    semantic_model_id: str,
) -> ParsedSemanticModelResponse:
    table_expression = (
        "let\n"
        '    Source = Sql.Database("sql.example.com"),\n'
        '    Database = Source{[Name="Analytics",Kind="Database"]}[Data],\n'
        '    Schema = Database{[Name="dbo",Kind="Schema"]}[Data],\n'
        '    Table = Schema{[Name="FactSales",Kind="Table"]}[Data]\n'
        "in\n"
        "    Table"
    )
    view_expression = (
        "let\n"
        '    Source = Sql.Database("sql.example.com"),\n'
        '    Database = Source{[Name="Analytics",Kind="Database"]}[Data],\n'
        '    Schema = Database{[Name="dbo",Kind="Schema"]}[Data],\n'
        '    View = Schema{[Name="VwSalesSummary",Kind="View"]}[Data]\n'
        "in\n"
        "    View"
    )
    return ParsedSemanticModelResponse(
        workspace_id=workspace_id,
        semantic_model_id=semantic_model_id,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Sales",
                        source_type="m",
                        expression=table_expression,
                    )
                ],
            ),
            ParsedSemanticModelTable(
                name="SalesArchive",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="SalesArchive",
                        source_type="m",
                        expression=table_expression,
                    )
                ],
            ),
            ParsedSemanticModelTable(
                name="SalesSummary",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="SalesSummary",
                        source_type="m",
                        expression=view_expression,
                    )
                ],
            ),
        ],
    )
