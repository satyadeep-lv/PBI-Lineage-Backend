import pytest

from app.api.dependencies.credentials import (
    get_bearer_token,
    get_fabric_access_token,
    get_powerbi_access_token,
)
from app.api.dependencies.lineage import get_lineage_store
from app.main import app
from app.repositories.lineage_repository import LineageRepository
from app.schemas.lineage_graph import LineageGraphBuildRequest
from app.services.auth.snowflake_auth_service import SnowflakeAuthService
from app.services.lineage_graph_service import LineageGraphService
from app.services.lineage_store_service import LineageStoreService
from app.services.live_lineage_scan_service import LiveLineageScanService
from app.services.snowflake_lineage_service import SnowflakeLineageService


@pytest.fixture(autouse=True)
def override_lineage_store(tmp_path):
    store = LineageStoreService(LineageRepository(tmp_path / "lineage.db"))
    app.dependency_overrides[get_lineage_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_lineage_store, None)


def _graph_request(*, include_measure: bool = False) -> dict:
    table = {
        "name": "Sales",
        "columns": [{"name": "Amount"}],
        "partitions": [
            {
                "name": "Sales",
                "source_type": "m",
                "expression": 'Sql.Database("sql.example.com", "warehouse")',
            }
        ],
    }
    if include_measure:
        table["measures"] = [
            {
                "name": "Total Sales",
                "expression": "SUM(Sales[Amount])",
            }
        ]
    return {
        "semantic_model": {
            "workspace_id": "workspace-1",
            "semantic_model_id": "model-1",
            "format": "TMDL",
            "tables": [table],
        }
    }


def test_build_get_search_validate_and_compare_graph_versions(client):
    first = client.post("/api/v1/lineage/graphs", json=_graph_request())
    second = client.post(
        "/api/v1/lineage/graphs",
        json=_graph_request(include_measure=True),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    graph_id = first.json()["graph"]["graph_id"]
    assert second.json()["metadata"]["version"] == 2

    stored = client.get(f"/api/v1/lineage/graphs/{graph_id}")
    search = client.get(
        f"/api/v1/lineage/graphs/{graph_id}/search",
        params={"query": "Total Sales"},
    )
    validation = client.get(f"/api/v1/lineage/graphs/{graph_id}/validate")
    changes = client.get(
        f"/api/v1/lineage/graphs/{graph_id}/changes",
        params={"from_version": 1, "to_version": 2},
    )

    assert stored.status_code == 200
    assert stored.json()["metadata"]["version"] == 2
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert validation.json()["valid"] is True
    assert changes.json()["has_changes"] is True


def test_dax_and_physical_source_analysis_endpoints(client):
    semantic_model = _graph_request(include_measure=True)["semantic_model"]

    dax = client.post("/api/v1/lineage/dax/analyze", json=semantic_model)
    physical = client.post(
        "/api/v1/lineage/physical-sources/analyze",
        json={"semantic_model": semantic_model},
    )

    assert dax.status_code == 200
    assert dax.json()["dependency_count"] == 1
    assert physical.status_code == 200
    assert physical.json()["source_count"] == 1


def test_snowflake_discovery_uses_bearer_token(client, monkeypatch):
    captured: dict[str, str | None] = {}

    async def fake_discover_lineage(
        self,
        *,
        account_identifier,
        access_token,
        warehouse=None,
        role=None,
        token_type="OAUTH",
    ):
        captured.update(
            account_identifier=account_identifier,
            access_token=access_token,
            warehouse=warehouse,
            role=role,
            token_type=token_type,
        )
        return SnowflakeLineageService().normalize_rows(
            account_identifier=account_identifier,
            rows=[],
        )

    monkeypatch.setattr(
        SnowflakeAuthService,
        "discover_lineage",
        fake_discover_lineage,
    )
    app.dependency_overrides[get_bearer_token] = lambda: "snowflake-token"
    try:
        response = client.post(
            "/api/v1/lineage/snowflake/discover",
            json={
                "account_identifier": "organization-account",
                "warehouse": "LINEAGE_WH",
                "role": "LINEAGE_READER",
            },
        )
    finally:
        app.dependency_overrides.pop(get_bearer_token, None)

    assert response.status_code == 200
    assert response.json()["account_identifier"] == "organization-account"
    assert captured == {
        "account_identifier": "organization-account",
        "access_token": "snowflake-token",
        "warehouse": "LINEAGE_WH",
        "role": "LINEAGE_READER",
        "token_type": "OAUTH",
    }


def test_live_graph_endpoint_uses_both_provider_tokens(client, monkeypatch):
    captured: dict[str, str] = {}

    async def fake_build_graph(
        self,
        request,
        *,
        fabric_access_token,
        powerbi_access_token,
    ):
        captured["fabric"] = fabric_access_token
        captured["powerbi"] = powerbi_access_token
        return LineageGraphService().build(
            LineageGraphBuildRequest.model_validate(_graph_request())
        )

    monkeypatch.setattr(LiveLineageScanService, "build_graph", fake_build_graph)
    app.dependency_overrides[get_fabric_access_token] = lambda: "fabric-token"
    app.dependency_overrides[get_powerbi_access_token] = lambda: "powerbi-token"
    try:
        response = client.post(
            "/api/v1/lineage/live-graphs",
            json={
                "semantic_model_workspace_id": "workspace-1",
                "semantic_model_id": "model-1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_fabric_access_token, None)
        app.dependency_overrides.pop(get_powerbi_access_token, None)

    assert response.status_code == 201
    assert response.json()["graph"]["node_count"] > 0
    assert captured == {
        "fabric": "fabric-token",
        "powerbi": "powerbi-token",
    }


def test_missing_graph_uses_structured_error(client):
    response = client.get("/api/v1/lineage/graphs/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
