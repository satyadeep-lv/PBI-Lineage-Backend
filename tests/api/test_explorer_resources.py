from datetime import UTC, datetime

import pytest

from app.api.dependencies.credentials import (
    get_fabric_access_token,
    get_powerbi_access_token,
)
from app.main import app
from app.schemas.explorer import (
    ExplorerSnapshotResponse,
    MeasureSourceLineageDataset,
    ReportLayoutDataset,
    SemanticModelObjectsDataset,
    SourceDatabaseLineageDataset,
    VisualSourceLookupDataset,
)
from app.services.explorer_service import ExplorerService

WORKSPACE_ID = "f089354e-8366-4e18-aea3-4cb4a3a50b48"
REPORT_ID = "879445d6-3a9e-4a74-b5ae-7c0ddabf0f11"
MODEL_ID = "cfafbeb1-8037-4d0c-896e-a46fb27ff229"


@pytest.fixture(autouse=True)
def override_authentication():
    app.dependency_overrides[get_fabric_access_token] = lambda: "fabric-token"
    app.dependency_overrides[get_powerbi_access_token] = lambda: "powerbi-token"
    yield
    app.dependency_overrides.pop(get_fabric_access_token, None)
    app.dependency_overrides.pop(get_powerbi_access_token, None)


@pytest.mark.parametrize(
    ("path", "expected_dataset"),
    [
        ("/api/v1/explorer/snapshot", None),
        (
            "/api/v1/explorer/source-database-lineage",
            "source_database_lineage",
        ),
        (
            "/api/v1/explorer/semantic-model-objects",
            "semantic_model_objects",
        ),
        (
            "/api/v1/explorer/measure-source-lineage",
            "measure_source_lineage",
        ),
        ("/api/v1/explorer/report-layout", "report_layout"),
        (
            "/api/v1/explorer/visual-source-lookup",
            "visual_source_lookup",
        ),
    ],
)
def test_explorer_routes_request_only_the_required_dataset(
    client,
    monkeypatch,
    path,
    expected_dataset,
):
    captured = {}

    async def fake_build_snapshot(
        self,
        request,
        *,
        fabric_access_token,
        powerbi_access_token,
        datasets=None,
    ):
        captured["fabric"] = fabric_access_token
        captured["powerbi"] = powerbi_access_token
        captured["datasets"] = datasets
        return _empty_snapshot()

    monkeypatch.setattr(
        ExplorerService,
        "build_snapshot",
        fake_build_snapshot,
    )
    response = client.post(path, json=_request_payload())

    assert response.status_code == 200
    assert captured["fabric"] == "fabric-token"
    assert captured["powerbi"] == "powerbi-token"
    assert captured["datasets"] == (
        None if expected_dataset is None else frozenset({expected_dataset})
    )
    if expected_dataset is None:
        assert "source_database_lineage" in response.json()
    else:
        assert response.json()["rows"] == []
        assert response.json()["count"] == 0


def test_explorer_request_rejects_duplicate_reports(client):
    payload = _request_payload()
    payload["reports"].append(dict(payload["reports"][0]))

    response = client.post("/api/v1/explorer/snapshot", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"


def _request_payload() -> dict:
    return {
        "reports": [
            {
                "workspace_id": WORKSPACE_ID,
                "report_id": REPORT_ID,
                "semantic_model_id": MODEL_ID,
            }
        ]
    }


def _empty_snapshot() -> ExplorerSnapshotResponse:
    return ExplorerSnapshotResponse(
        generated_at=datetime.now(UTC),
        report_count=0,
        semantic_model_count=0,
        source_database_lineage=SourceDatabaseLineageDataset(),
        semantic_model_objects=SemanticModelObjectsDataset(),
        measure_source_lineage=MeasureSourceLineageDataset(),
        report_layout=ReportLayoutDataset(),
        visual_source_lookup=VisualSourceLookupDataset(),
    )
