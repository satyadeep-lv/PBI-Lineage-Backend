import pytest

from app.api.dependencies.credentials import (
    get_fabric_access_token,
    get_powerbi_access_token,
)
from app.main import app
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelResponse,
)
from app.schemas.report import Report
from app.schemas.report_definition import (
    ReportDefinition,
    ReportDefinitionPart,
    ReportDefinitionResponse,
)
from app.schemas.report_page import (
    ReportPage,
    ReportPageListResponse,
)
from app.schemas.report_semantic_lineage import (
    ReportSemanticLineageResponse,
    SemanticLineageDiagnosticsSummary,
)
from app.schemas.semantic_model_definition import (
    SemanticModelDefinition,
    SemanticModelDefinitionPart,
    SemanticModelDefinitionResponse,
)
from app.schemas.semantic_model_metadata import (
    SemanticModelMetadataReconciliation,
    SemanticModelMetadataResponse,
)
from app.schemas.xmla_metadata import (
    XmlaSemanticModelMetadataResponse,
    XmlaSemanticModelTable,
)
from app.services.report_definition_service import (
    ReportDefinitionService,
)
from app.services.report_semantic_lineage_service import (
    ReportSemanticLineageService,
)
from app.services.report_service import (
    ReportService,
)
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.semantic_model_metadata_service import (
    SemanticModelMetadataService,
)
from app.services.xmla_metadata_service import (
    XmlaMetadataService,
)

WORKSPACE_ID = "f089354e-8366-4e18-aea3-4cb4a3a50b48"

REPORT_ID = "879445d6-3a9e-4a74-b5ae-7c0ddabf0f11"

SEMANTIC_MODEL_ID = "cfafbeb1-8037-4d0c-896e-a46fb27ff229"


@pytest.fixture(autouse=True)
def override_authentication():
    async def fake_powerbi_token() -> str:
        return "fake-test-token"

    async def fake_fabric_token() -> str:
        return "fake-fabric-token"

    app.dependency_overrides[get_powerbi_access_token] = fake_powerbi_token
    app.dependency_overrides[get_fabric_access_token] = fake_fabric_token

    yield

    app.dependency_overrides.pop(
        get_powerbi_access_token,
        None,
    )
    app.dependency_overrides.pop(
        get_fabric_access_token,
        None,
    )


def test_get_report(
    client,
    monkeypatch,
):
    async def fake_get_report(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
    ) -> Report:
        return Report(
            id=report_id,
            name="Sales Report",
            dataset_id="dataset-1",
            report_type="PowerBIReport",
            format="PBIR",
        )

    monkeypatch.setattr(
        ReportService,
        "get_report",
        fake_get_report,
    )

    response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}")

    assert response.status_code == 200

    payload = response.json()

    assert payload["id"] == REPORT_ID
    assert payload["name"] == "Sales Report"
    assert payload["format"] == "PBIR"


def test_get_my_workspace_report(
    client,
    monkeypatch,
):
    async def fake_get_my_workspace_report(
        self,
        *,
        report_id: str,
        access_token: str,
    ) -> Report:
        assert access_token == "fake-test-token"

        return Report(
            id=report_id,
            name="My Workspace Sales Report",
            dataset_id="dataset-1",
        )

    monkeypatch.setattr(
        ReportService,
        "get_my_workspace_report",
        fake_get_my_workspace_report,
    )

    response = client.get(f"/api/v1/reports/{REPORT_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == REPORT_ID
    assert response.json()["name"] == "My Workspace Sales Report"


def test_list_report_pages(
    client,
    monkeypatch,
):
    async def fake_list_pages(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
    ) -> ReportPageListResponse:
        return ReportPageListResponse(
            workspace_id=workspace_id,
            report_id=report_id,
            pages=[
                ReportPage(
                    name="ReportSection",
                    display_name=("Executive Summary"),
                    order=0,
                )
            ],
            count=1,
        )

    monkeypatch.setattr(
        ReportService,
        "list_pages",
        fake_list_pages,
    )

    response = client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/pages"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["count"] == 1

    assert payload["pages"][0]["name"] == "ReportSection"


def test_get_report_page(
    client,
    monkeypatch,
):
    async def fake_get_page(
        self,
        *,
        workspace_id: str,
        report_id: str,
        page_name: str,
        access_token: str,
    ) -> ReportPage:
        return ReportPage(
            name=page_name,
            display_name="Executive Summary",
            order=0,
        )

    monkeypatch.setattr(
        ReportService,
        "get_page",
        fake_get_page,
    )

    response = client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/pages/ReportSection"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["name"] == "ReportSection"

    assert payload["display_name"] == "Executive Summary"


def test_invalid_report_uuid(
    client,
):
    response = client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/reports/invalid-report-id"
    )

    assert response.status_code == 422


def test_get_report_definition_uses_pbir_default(
    client,
    monkeypatch,
):
    async def fake_get_definition(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
        definition_format: str,
    ) -> ReportDefinitionResponse:
        assert workspace_id == WORKSPACE_ID
        assert report_id == REPORT_ID
        assert access_token == "fake-fabric-token"
        assert definition_format == "PBIR"

        return ReportDefinitionResponse(
            workspace_id=workspace_id,
            report_id=report_id,
            definition=ReportDefinition(
                format=definition_format,
                parts=[
                    ReportDefinitionPart(
                        path="definition.pbir",
                        payload="e30=",
                        payload_type=("InlineBase64"),
                    )
                ],
            ),
        )

    monkeypatch.setattr(
        ReportDefinitionService,
        "get_definition",
        fake_get_definition,
    )

    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/definition"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["definition"]["format"] == "PBIR"


def test_report_definition_rejects_semantic_model_format(
    client,
):
    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/definition?format=TMDL"
    )

    assert response.status_code == 422


def test_normalized_report_definition_rejects_semantic_model_format(
    client,
):
    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        f"reports/{REPORT_ID}/definition/normalized"
        "?format=TMDL"
    )

    assert response.status_code == 422


def test_get_semantic_model_definition(
    client,
    monkeypatch,
):
    async def fake_get_definition(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        definition_format: str,
    ) -> SemanticModelDefinitionResponse:
        assert workspace_id == WORKSPACE_ID
        assert semantic_model_id == SEMANTIC_MODEL_ID
        assert access_token == "fake-fabric-token"
        assert definition_format == "TMSL"

        return SemanticModelDefinitionResponse(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            definition=SemanticModelDefinition(
                format=definition_format,
                parts=[
                    SemanticModelDefinitionPart(
                        path=("definition/model.tmdl"),
                        payload=("bW9kZWwgTW9kZWw="),
                        payload_type=("InlineBase64"),
                    )
                ],
            ),
        )

    monkeypatch.setattr(
        SemanticModelDefinitionService,
        "get_definition",
        fake_get_definition,
    )

    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        "semantic-models/"
        f"{SEMANTIC_MODEL_ID}/definition"
        "?format=TMSL"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["workspace_id"] == WORKSPACE_ID
    assert payload["semantic_model_id"] == SEMANTIC_MODEL_ID
    assert payload["definition"]["format"] == "TMSL"
    assert payload["definition"]["parts"][0]["payloadType"] == "InlineBase64"
    assert "payload_type" not in payload["definition"]["parts"][0]


def test_semantic_model_definition_rejects_invalid_format(
    client,
):
    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        "semantic-models/"
        f"{SEMANTIC_MODEL_ID}/definition"
        "?format=PBIR"
    )

    assert response.status_code == 422


def test_get_semantic_model_xmla_metadata(
    client,
    monkeypatch,
):
    async def fake_get_metadata(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        workspace_name: str | None,
        database_name: str | None,
    ) -> XmlaSemanticModelMetadataResponse:
        assert workspace_id == WORKSPACE_ID
        assert semantic_model_id == SEMANTIC_MODEL_ID
        assert access_token == "fake-test-token"
        assert workspace_name == "Sales Workspace"
        assert database_name == "Sales Model"

        return XmlaSemanticModelMetadataResponse(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            xmla_endpoint=("powerbi://api.powerbi.com/v1.0/myorg/Sales Workspace"),
            database_name=database_name,
            table_count=1,
            column_count=0,
            measure_count=0,
            relationship_count=0,
            hierarchy_count=0,
            partition_count=0,
            tables=[XmlaSemanticModelTable(name="Sales")],
        )

    monkeypatch.setattr(
        XmlaMetadataService,
        "get_metadata",
        fake_get_metadata,
    )

    response = client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        "semantic-models/"
        f"{SEMANTIC_MODEL_ID}/xmla/metadata"
        "?workspaceName=Sales%20Workspace"
        "&databaseName=Sales%20Model"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["workspace_id"] == WORKSPACE_ID
    assert payload["semantic_model_id"] == SEMANTIC_MODEL_ID
    assert payload["source"] == "xmla"
    assert (
        payload["xmla_endpoint"] == "powerbi://api.powerbi.com/v1.0/"
        "myorg/Sales Workspace"
    )
    assert payload["database_name"] == "Sales Model"
    assert payload["table_count"] == 1
    assert payload["tables"][0]["name"] == "Sales"


def test_get_semantic_model_metadata(
    client,
    monkeypatch,
):
    async def fake_get_metadata(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        fabric_access_token: str,
        powerbi_access_token: str,
        workspace_name: str | None,
        database_name: str | None,
        definition_format: str,
    ) -> SemanticModelMetadataResponse:
        assert workspace_id == WORKSPACE_ID
        assert semantic_model_id == SEMANTIC_MODEL_ID
        assert fabric_access_token == "fake-fabric-token"
        assert powerbi_access_token == "fake-test-token"
        assert workspace_name == "Sales Workspace"
        assert database_name == "Sales Model"
        assert definition_format == "TMDL"

        return SemanticModelMetadataResponse(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            definition=ParsedSemanticModelResponse(
                workspace_id=workspace_id,
                semantic_model_id=semantic_model_id,
                format="TMDL",
            ),
            xmla=XmlaSemanticModelMetadataResponse(
                workspace_id=workspace_id,
                semantic_model_id=semantic_model_id,
                xmla_endpoint=(
                    "powerbi://api.powerbi.com/v1.0/myorg/Sales%20Workspace"
                ),
                table_count=0,
                column_count=0,
                measure_count=0,
                relationship_count=0,
                hierarchy_count=0,
                partition_count=0,
            ),
            reconciliation=(
                SemanticModelMetadataReconciliation(
                    matched_count=0,
                    definition_only_count=0,
                    xmla_only_count=0,
                )
            ),
        )

    monkeypatch.setattr(
        SemanticModelMetadataService,
        "get_metadata",
        fake_get_metadata,
    )

    response = client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        "semantic-models/"
        f"{SEMANTIC_MODEL_ID}/metadata"
        "?workspaceName=Sales%20Workspace"
        "&databaseName=Sales%20Model"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["workspace_id"] == WORKSPACE_ID
    assert payload["semantic_model_id"] == SEMANTIC_MODEL_ID
    assert payload["definition"]["format"] == "TMDL"
    assert payload["xmla"]["source"] == "xmla"
    assert payload["reconciliation"] == {
        "matched_count": 0,
        "definition_only_count": 0,
        "xmla_only_count": 0,
        "matches": [],
    }


def test_semantic_model_metadata_rejects_non_tmdl_format(
    client,
):
    response = client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        "semantic-models/"
        f"{SEMANTIC_MODEL_ID}/metadata?format=TMSL"
    )

    assert response.status_code == 422


def test_get_report_semantic_lineage(
    client,
    monkeypatch,
):
    expected_semantic_model_workspace_id = "a2f8996f-8f1a-46e3-8f7c-3f2d2145df45"

    async def fake_build_lineage(
        self,
        *,
        workspace_id: str,
        report_id: str,
        semantic_model_workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        report_definition_format: str | None,
        semantic_model_definition_format: str,
    ) -> ReportSemanticLineageResponse:
        assert workspace_id == WORKSPACE_ID
        assert report_id == REPORT_ID
        assert semantic_model_workspace_id == expected_semantic_model_workspace_id
        assert semantic_model_id == SEMANTIC_MODEL_ID
        assert access_token == "fake-fabric-token"
        assert report_definition_format == "PBIR"
        assert semantic_model_definition_format == "TMDL"

        return ReportSemanticLineageResponse(
            workspace_id=workspace_id,
            report_id=report_id,
            semantic_model_workspace_id=(semantic_model_workspace_id),
            semantic_model_id=semantic_model_id,
            total_field_reference_count=1,
            matched_field_reference_count=1,
            unmatched_field_reference_count=0,
            diagnostics_summary=(
                SemanticLineageDiagnosticsSummary(
                    status_counts={
                        "matched": 1,
                        "unmatched": 0,
                    }
                )
            ),
        )

    monkeypatch.setattr(
        ReportSemanticLineageService,
        "build_lineage",
        fake_build_lineage,
    )

    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        f"reports/{REPORT_ID}/semantic-lineage"
        f"?semantic_model_id={SEMANTIC_MODEL_ID}"
        "&semanticModelFormat=TMDL"
        "&semantic_model_workspace_id="
        f"{expected_semantic_model_workspace_id}"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["workspace_id"] == WORKSPACE_ID
    assert payload["report_id"] == REPORT_ID
    assert (
        payload["semantic_model_workspace_id"] == expected_semantic_model_workspace_id
    )
    assert payload["semantic_model_id"] == SEMANTIC_MODEL_ID
    assert payload["matched_field_reference_count"] == 1
    assert payload["diagnostics_summary"]["status_counts"] == {
        "matched": 1,
        "unmatched": 0,
    }


def test_report_semantic_lineage_rejects_semantic_model_format_for_report(
    client,
):
    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        f"reports/{REPORT_ID}/semantic-lineage"
        f"?semantic_model_id={SEMANTIC_MODEL_ID}"
        "&reportFormat=TMDL"
    )

    assert response.status_code == 422


def test_report_semantic_lineage_rejects_report_format_for_semantic_model(
    client,
):
    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/"
        f"reports/{REPORT_ID}/semantic-lineage"
        f"?semantic_model_id={SEMANTIC_MODEL_ID}"
        "&semanticModelFormat=PBIR"
    )

    assert response.status_code == 422
