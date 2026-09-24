from collections import Counter
from types import SimpleNamespace

import pytest

from app.api.dependencies.credentials import (
    get_optional_fabric_access_token,
    get_powerbi_access_token,
)
from app.core.exceptions import ProviderResourceNotFoundError
from app.main import app
from app.schemas.explorer import ReportVisualSourceColumnsRequest
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
    NormalizedReportPage,
    NormalizedReportVisual,
    SemanticModelReference,
    VisualFieldReference,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelExpression,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.report import Report
from app.schemas.semantic_model import SemanticModel, SemanticModelListResponse
from app.schemas.workspace import Workspace, WorkspaceListResponse
from app.services.gateway_service import GatewayService
from app.services.report_definition_normalizer import ReportDefinitionNormalizer
from app.services.report_definition_service import ReportDefinitionService
from app.services.report_service import ReportService
from app.services.semantic_model_definition_parser import (
    SemanticModelDefinitionParser,
)
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.semantic_model_service import SemanticModelService
from app.services.workspace_service import WorkspaceService

_REAL_GET_NORMALIZED_DEFINITION = ReportDefinitionService.get_normalized_definition
_REAL_GET_PARSED_DEFINITION = SemanticModelDefinitionService.get_parsed_definition

PATH = "/api/v1/explorer/report-visual-source-columns"

WORKSPACE_ID = "f089354e-8366-4e18-aea3-4cb4a3a50b48"
REPORT_ID = "879445d6-3a9e-4a74-b5ae-7c0ddabf0f11"
MODEL_ID = "cfafbeb1-8037-4d0c-896e-a46fb27ff229"
MODEL_WORKSPACE_ID = "5b1f2c7e-0000-4000-8000-000000000001"
UPSTREAM_WORKSPACE_ID = "33333333-3333-3333-3333-333333333333"
UPSTREAM_MODEL_ID = "44444444-4444-4444-4444-444444444444"

SNOWFLAKE = 'Snowflake.Databases("acme.snowflakecomputing.com", "WH")'


def _snowflake_table(database: str, schema: str, table: str) -> str:
    return (
        f"{SNOWFLAKE}"
        f'{{[Name="{database}",Kind="Database"]}}[Data]'
        f'{{[Name="{schema}",Kind="Schema"]}}[Data]'
        f'{{[Name="{table}",Kind="Table"]}}[Data]'
    )


def _import_partition(name: str, expression: str) -> ParsedSemanticModelPartition:
    return ParsedSemanticModelPartition(
        name=name,
        source_type="m",
        mode="import",
        expression=expression,
    )


def _primary_model(workspace_id: str, model_id: str) -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id=workspace_id,
        semantic_model_id=model_id,
        format="TMDL",
        expressions=[
            ParsedSemanticModelExpression(
                name="DirectQuery to AS - Upstream Model",
                expression=(
                    "let\n    Source = AnalysisServices.Database("
                    '"powerbi://api.powerbi.com/v1.0/myorg/DEV", "Upstream Model")'
                    "\nin\n    Source"
                ),
            )
        ],
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                columns=[
                    ParsedSemanticModelColumn(name="Amount", source_column="AMOUNT"),
                    ParsedSemanticModelColumn(name="Region", source_column="REGION"),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Revenue",
                        expression="SUM('Sales'[Amount])",
                    ),
                    # measure -> measure -> column
                    ParsedSemanticModelMeasure(
                        name="Margin",
                        expression="[Revenue] * 0.2",
                    ),
                    # two columns from two tables
                    ParsedSemanticModelMeasure(
                        name="Net Revenue",
                        expression="SUM('Sales'[Amount]) - SUM('Customer'[Discount])",
                    ),
                    # a dependency cycle
                    ParsedSemanticModelMeasure(name="Loop A", expression="[Loop B]"),
                    ParsedSemanticModelMeasure(name="Loop B", expression="[Loop A]"),
                ],
                partitions=[
                    _import_partition(
                        "Sales",
                        _snowflake_table("ANALYTICS", "MART", "FACT_SALES"),
                    )
                ],
            ),
            ParsedSemanticModelTable(
                name="Customer",
                columns=[
                    ParsedSemanticModelColumn(
                        name="Discount",
                        source_column="DISCOUNT_PCT",
                    ),
                ],
                partitions=[
                    _import_partition(
                        "Customer",
                        _snowflake_table("ANALYTICS", "MART", "DIM_CUSTOMER"),
                    )
                ],
            ),
            # A composite (DirectQuery to semantic model) table.
            ParsedSemanticModelTable(
                name="Employees",
                source_lineage_tag="tag-employees",
                columns=[
                    ParsedSemanticModelColumn(
                        name="Employee Name",
                        source_column="Full Name",
                    ),
                ],
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Employees",
                        source_type="entity",
                        mode="directQuery",
                        entity_name="EMPLOYEES",
                        expression_source="DirectQuery to AS - Upstream Model",
                    )
                ],
            ),
        ],
    )


def _upstream_model(workspace_id: str, model_id: str) -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id=workspace_id,
        semantic_model_id=model_id,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="EMPLOYEES",
                lineage_tag="tag-employees",
                columns=[
                    # The composite column's sourceColumn names this upstream
                    # column; the database column is one step further.
                    ParsedSemanticModelColumn(
                        name="Full Name",
                        source_column="FULL_NAME",
                    ),
                ],
                partitions=[
                    _import_partition(
                        "EMPLOYEES",
                        _snowflake_table("POC_DB", "HUMAN_RESOURCES", "EMPLOYEES"),
                    )
                ],
            )
        ],
    )


def _field(
    object_type: str,
    table_name: str | None,
    object_name: str,
    *,
    role: str = "Values",
    aggregation_function: int | None = None,
) -> VisualFieldReference:
    return VisualFieldReference(
        object_type=object_type,
        table_name=table_name,
        object_name=object_name,
        usage="projection",
        role=role,
        aggregation_function=aggregation_function,
    )


VISUAL_FIELDS = {
    "visual-amount": _field("column", "Sales", "Amount", aggregation_function=0),
    "visual-margin": _field("measure", "Sales", "Margin"),
    "visual-net": _field("measure", "Sales", "Net Revenue"),
    "visual-employee": _field("column", "Employees", "Employee Name", role="Rows"),
    "visual-ghost": _field("measure", "Sales", "Ghost Measure"),
    "visual-calc": _field("visual_calculation", None, "Running total"),
    "visual-loop": _field("measure", "Sales", "Loop A"),
}


def _report_definition(
    workspace_id: str,
    report_id: str,
) -> NormalizedReportDefinitionResponse:
    visuals = [
        NormalizedReportVisual(
            id=visual_id,
            internal_name=visual_id,
            title=visual_id.replace("-", " ").title(),
            visual_type="tableEx",
            has_query=True,
            field_references=[reference],
        )
        for visual_id, reference in VISUAL_FIELDS.items()
    ]
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
                name="ReportSection1",
                display_name="Overview",
                order=0,
                visuals=visuals,
                visual_count=len(visuals),
            )
        ],
        page_count=1,
        visual_count=len(visuals),
        source_part_count=4,
        decoded_json_part_count=4,
        warnings=[],
    )


class _Provider:
    """Fakes every provider read; lineage logic itself runs for real."""

    def __init__(self) -> None:
        self.calls: Counter = Counter()
        self.workspaces = {
            WORKSPACE_ID: "POC",
            MODEL_WORKSPACE_ID: "Shared Models",
            UPSTREAM_WORKSPACE_ID: "DEV",
        }
        self.models_by_workspace = {
            WORKSPACE_ID: [],
            MODEL_WORKSPACE_ID: [SemanticModel(id=MODEL_ID, name="sales")],
            UPSTREAM_WORKSPACE_ID: [
                SemanticModel(id=UPSTREAM_MODEL_ID, name="Upstream Model")
            ],
        }
        self.definitions = {
            (MODEL_WORKSPACE_ID, MODEL_ID): _primary_model,
            (UPSTREAM_WORKSPACE_ID, UPSTREAM_MODEL_ID): _upstream_model,
        }
        self.model_definition_error: Exception | None = None

    def install(self, monkeypatch) -> None:
        provider = self

        async def get_workspace(self, *, workspace_id, access_token):
            provider.calls["workspace"] += 1
            return Workspace(id=workspace_id, name=provider.workspaces[workspace_id])

        async def list_workspaces(self, *, access_token, top, skip):
            provider.calls["list_workspaces"] += 1
            workspaces = [
                Workspace(id=workspace_id, name=name)
                for workspace_id, name in provider.workspaces.items()
            ]
            return WorkspaceListResponse(
                workspaces=workspaces,
                count=len(workspaces),
                top=top,
                skip=skip,
            )

        async def get_report(self, *, workspace_id, report_id, access_token):
            provider.calls["report"] += 1
            # No datasetWorkspaceId, as the live tenant returns it.
            return Report(id=report_id, name="Sales Report", dataset_id=MODEL_ID)

        async def get_normalized_definition(
            self,
            *,
            workspace_id,
            report_id,
            access_token,
            definition_format,
        ):
            provider.calls["report_definition"] += 1
            assert access_token == "fabric-token"
            return _report_definition(workspace_id, report_id)

        async def get_parsed_definition(
            self,
            *,
            workspace_id,
            semantic_model_id,
            access_token,
            definition_format,
        ):
            provider.calls["model_definition"] += 1
            assert access_token == "fabric-token"
            if provider.model_definition_error is not None:
                raise provider.model_definition_error
            factory = provider.definitions.get((workspace_id, semantic_model_id))
            if factory is None:
                raise ProviderResourceNotFoundError("fabric", "semantic model")
            return factory(workspace_id, semantic_model_id)

        async def list_semantic_models(self, *, workspace_id, access_token):
            provider.calls["list_models"] += 1
            models = provider.models_by_workspace.get(workspace_id, [])
            return SemanticModelListResponse(
                workspace_id=workspace_id,
                semantic_models=models,
                count=len(models),
            )

        async def list_gateways(self, *, access_token):
            provider.calls["gateways"] += 1
            raise AssertionError("Gateway calls must stay opt-in.")

        monkeypatch.setattr(WorkspaceService, "get_workspace", get_workspace)
        monkeypatch.setattr(WorkspaceService, "list_workspaces", list_workspaces)
        monkeypatch.setattr(ReportService, "get_report", get_report)
        monkeypatch.setattr(
            ReportDefinitionService,
            "get_normalized_definition",
            get_normalized_definition,
        )
        monkeypatch.setattr(
            SemanticModelDefinitionService,
            "get_parsed_definition",
            get_parsed_definition,
        )
        monkeypatch.setattr(
            SemanticModelService,
            "list_semantic_models",
            list_semantic_models,
        )
        monkeypatch.setattr(GatewayService, "list_gateways", list_gateways)


@pytest.fixture(autouse=True)
def override_authentication():
    app.dependency_overrides[get_powerbi_access_token] = lambda: "powerbi-token"
    app.dependency_overrides[get_optional_fabric_access_token] = lambda: "fabric-token"
    yield
    app.dependency_overrides.pop(get_powerbi_access_token, None)
    app.dependency_overrides.pop(get_optional_fabric_access_token, None)


@pytest.fixture
def provider(monkeypatch) -> _Provider:
    fake = _Provider()
    fake.install(monkeypatch)
    return fake


def _payload() -> dict:
    return {"workspace_id": WORKSPACE_ID, "report_id": REPORT_ID}


def _rows_by_visual(body: dict) -> dict[str, dict]:
    return {row["visual_id"]: row for row in body["rows"]}


def test_plain_column_resolves_to_its_source_column_and_table(client, provider):
    response = client.post(PATH, json=_payload())

    assert response.status_code == 200
    row = _rows_by_visual(response.json())["visual-amount"]
    assert row["semantic_table"] == "Sales"
    assert row["semantic_object_name"] == "Amount"
    assert row["semantic_object_type"] == "column"
    assert row["field_role"] == "Values"
    assert row["page_name"] == "Overview"
    assert row["source_columns"] == ["AMOUNT"]
    assert row["source_tables"] == ["ANALYTICS.MART.FACT_SALES"]
    assert row["via_workspace_name"] is None
    assert row["resolution_status"] == "resolved"
    # An implicit aggregation is traced through its column and says so.
    assert "Implicit measure: Sum" in row["resolution_note"]


def test_measure_chain_resolves_to_the_terminal_columns(client, provider):
    body = client.post(PATH, json=_payload()).json()

    row = _rows_by_visual(body)["visual-margin"]
    assert row["semantic_object_type"] == "measure"
    assert row["dax_expression"] == "[Revenue] * 0.2"
    assert row["source_columns"] == ["AMOUNT"]
    assert row["source_tables"] == ["ANALYTICS.MART.FACT_SALES"]
    assert row["resolution_status"] == "resolved"


def test_measure_reading_two_tables_returns_both(client, provider):
    body = client.post(PATH, json=_payload()).json()

    row = _rows_by_visual(body)["visual-net"]
    assert row["source_columns"] == ["AMOUNT", "DISCOUNT_PCT"]
    assert row["source_tables"] == [
        "ANALYTICS.MART.DIM_CUSTOMER",
        "ANALYTICS.MART.FACT_SALES",
    ]
    assert row["resolution_status"] == "resolved"


def test_cross_workspace_composite_table_reports_the_upstream_database(
    client,
    provider,
):
    body = client.post(PATH, json=_payload()).json()

    row = _rows_by_visual(body)["visual-employee"]
    # The upstream model's sourceColumn, not the composite column's.
    assert row["source_columns"] == ["FULL_NAME"]
    assert row["source_tables"] == ["POC_DB.HUMAN_RESOURCES.EMPLOYEES"]
    assert row["via_workspace_name"] == "DEV"
    assert row["resolution_status"] == "resolved"
    every_table = [table for r in body["rows"] for table in r["source_tables"]]
    assert not any("powerbi://" in table for table in every_table)


def test_unfollowable_composite_link_is_partial_or_unresolved_with_warning(
    client,
    provider,
):
    # The upstream workspace is not visible to the caller.
    del provider.workspaces[UPSTREAM_WORKSPACE_ID]

    body = client.post(PATH, json=_payload()).json()

    row = _rows_by_visual(body)["visual-employee"]
    assert row["resolution_status"] == "unresolved"
    assert row["source_columns"] == []
    assert row["source_tables"] == []
    assert "could not be followed" in row["resolution_note"]
    codes = {warning["code"] for warning in body["warnings"]}
    assert "CROSS_WORKSPACE_WORKSPACE_NOT_FOUND" in codes
    assert "CROSS_WORKSPACE_SOURCE_UNRESOLVED" in codes


def test_unmatched_field_and_visual_calculation_are_unresolved_without_invention(
    client,
    provider,
):
    body = client.post(PATH, json=_payload()).json()
    rows = _rows_by_visual(body)

    ghost = rows["visual-ghost"]
    assert ghost["resolution_status"] == "unresolved"
    assert ghost["source_columns"] == []
    assert ghost["source_tables"] == []
    assert "not in the semantic model" in ghost["resolution_note"]

    calculation = rows["visual-calc"]
    assert calculation["resolution_status"] == "unresolved"
    assert calculation["semantic_object_type"] is None
    assert calculation["source_columns"] == []
    assert "Visual calculation 'Running total'" in calculation["resolution_note"]


def test_dax_cycle_is_partial_with_the_existing_warning_code(client, provider):
    body = client.post(PATH, json=_payload()).json()

    row = _rows_by_visual(body)["visual-loop"]
    assert row["resolution_status"] == "partial"
    assert "DAX dependency cycle" in row["resolution_note"]
    assert "DAX_DEPENDENCY_CYCLE" in {warning["code"] for warning in body["warnings"]}


def test_response_counts_and_inferred_model_in_another_workspace(client, provider):
    body = client.post(PATH, json=_payload()).json()

    assert body["workspace_name"] == "POC"
    assert body["report_name"] == "Sales Report"
    # The report carries no datasetWorkspaceId and its own workspace does not
    # list the model, so the bound model is found by searching.
    assert body["semantic_model_id"] == MODEL_ID
    assert body["semantic_model_name"] == "sales"
    assert body["semantic_model_workspace_id"] == MODEL_WORKSPACE_ID
    assert body["total_field_reference_count"] == len(VISUAL_FIELDS)
    assert (
        body["resolved_count"] + body["partial_count"] + body["unresolved_count"]
        == body["total_field_reference_count"]
    )
    assert body["resolved_count"] == 4
    assert body["unresolved_count"] == 2


def test_gateway_sources_are_off_by_default_and_never_called(client, provider):
    assert (
        ReportVisualSourceColumnsRequest.model_validate(
            _payload()
        ).include_gateway_sources
        is False
    )

    response = client.post(PATH, json=_payload())

    assert response.status_code == 200
    assert provider.calls["gateways"] == 0


def test_unreadable_model_definition_degrades_to_unresolved_rows(client, provider):
    provider.model_definition_error = ProviderResourceNotFoundError(
        "fabric",
        "semantic model",
    )

    response = client.post(PATH, json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["total_field_reference_count"] == len(VISUAL_FIELDS)
    assert body["unresolved_count"] == len(VISUAL_FIELDS)
    assert all(row["source_columns"] == [] for row in body["rows"])
    assert "SEMANTIC_MODEL_DEFINITION_UNAVAILABLE" in {
        warning["code"] for warning in body["warnings"]
    }


def test_missing_report_uses_the_standard_error_envelope(
    client,
    provider,
    monkeypatch,
):
    async def missing_report(self, *, workspace_id, report_id, access_token):
        raise ProviderResourceNotFoundError("powerbi", "report")

    monkeypatch.setattr(ReportService, "get_report", missing_report)

    response = client.post(PATH, json=_payload())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_repeat_calls_reuse_cached_definitions_until_cache_is_cleared(
    client,
    provider,
    monkeypatch,
):
    # Restore the real definition reads so the session cache sits in the path,
    # and count the Fabric fetches underneath it instead.
    fetches: Counter = Counter()

    async def fetch_report(self, *, workspace_id, report_id, access_token, **_):
        fetches["report"] += 1
        return SimpleNamespace(workspace_id=workspace_id, report_id=report_id)

    async def fetch_model(
        self,
        *,
        workspace_id,
        semantic_model_id,
        access_token,
        **_,
    ):
        fetches[semantic_model_id] += 1
        return SimpleNamespace(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
        )

    monkeypatch.setattr(
        ReportDefinitionService,
        "get_normalized_definition",
        _REAL_GET_NORMALIZED_DEFINITION,
    )
    monkeypatch.setattr(
        SemanticModelDefinitionService,
        "get_parsed_definition",
        _REAL_GET_PARSED_DEFINITION,
    )
    monkeypatch.setattr(ReportDefinitionService, "_fetch_definition", fetch_report)
    monkeypatch.setattr(
        SemanticModelDefinitionService,
        "_fetch_definition",
        fetch_model,
    )
    monkeypatch.setattr(
        ReportDefinitionNormalizer,
        "normalize",
        lambda self, raw: _report_definition(raw.workspace_id, raw.report_id),
    )
    monkeypatch.setattr(
        SemanticModelDefinitionParser,
        "parse",
        lambda self, raw: provider.definitions[
            (raw.workspace_id, raw.semantic_model_id)
        ](raw.workspace_id, raw.semantic_model_id),
    )

    first = client.post(PATH, json=_payload())
    after_first = dict(fetches)
    second = client.post(PATH, json=_payload())

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert after_first == {"report": 1, MODEL_ID: 1, UPSTREAM_MODEL_ID: 1}
    assert dict(fetches) == after_first

    # Definitions are cached under the Fabric token; a refresh must clear
    # them too, not only the Power BI reads.
    assert client.delete("/api/v1/cache").json()["entry_count"] == 0
    client.post(PATH, json=_payload())

    assert dict(fetches) == {"report": 2, MODEL_ID: 2, UPSTREAM_MODEL_ID: 2}


def test_route_is_documented_under_explorer(client):
    operation = client.get("/openapi.json").json()["paths"][PATH]["post"]

    assert operation["tags"] == ["Explorer"]
    assert operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("ReportVisualSourceColumnsRequest")
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("ReportVisualSourceColumnsResponse")
    assert "404" in operation["responses"]
