from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.metrics import _normalized_route
from app.core.security import RequestBodyLimitMiddleware
from app.repositories.lineage_repository import LineageRepository
from app.services.operations_service import OperationsService


def test_security_headers_and_metrics_are_exposed(client):
    health = client.get("/api/v1/health/live")
    metrics = client.get("/api/v1/health/metrics")

    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["cache-control"] == "no-store"
    assert metrics.status_code == 200
    assert "pbi_lineage_http_requests_total" in metrics.text
    assert 'route="/api/v1/health/live"' in metrics.text


def test_readiness_checks_lineage_database(client, monkeypatch, tmp_path):
    repository = LineageRepository(tmp_path / "lineage.db")
    monkeypatch.setattr(
        "app.api.v1.health.get_lineage_repository",
        lambda: repository,
    )

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["lineage_database"]["status"] == "pass"


def test_lineage_api_key_is_enforced_when_configured(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.dependencies.security.get_settings",
        lambda: SimpleNamespace(
            lineage_admin_api_key=SecretStr("expected-key"),
        ),
    )
    semantic_model = {
        "workspace_id": "workspace-1",
        "semantic_model_id": "model-1",
    }

    missing = client.post("/api/v1/lineage/dax/analyze", json=semantic_model)
    invalid = client.post(
        "/api/v1/lineage/dax/analyze",
        json=semantic_model,
        headers={"X-Lineage-Admin-Key": "wrong-key"},
    )
    valid = client.post(
        "/api/v1/lineage/dax/analyze",
        json=semantic_model,
        headers={"X-Lineage-Admin-Key": "expected-key"},
    )

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "LINEAGE_API_KEY_REQUIRED"
    assert invalid.status_code == 403
    assert valid.status_code == 200


def test_request_body_limit_rejects_oversized_payload():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=8)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, str]:
        return {"body": (await request.body()).decode("utf-8")}

    with TestClient(app) as local_client:
        response = local_client.post(
            "/echo",
            content="123456789",
            headers={"Content-Type": "text/plain"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_BODY_TOO_LARGE"


def test_metrics_normalize_named_path_parameters():
    route = _normalized_route(
        "/api/v1/workspaces/workspace-1/reports/report-1/pages/Overview",
        {
            "workspace_id": "workspace-1",
            "report_id": "report-1",
            "page_name": "Overview",
        },
    )

    assert route == (
        "/api/v1/workspaces/{workspace_id}/reports/{report_id}/pages/{page_name}"
    )


def test_production_readiness_rejects_wildcard_cors(tmp_path):
    settings = Settings(
        environment="production",
        auth_cookie_secure=True,
        allowed_hosts=["api.example.com"],
        cors_allowed_origins=["*"],
        lineage_admin_api_key="secret",
    )
    readiness = OperationsService().readiness(
        settings=settings,
        repository=LineageRepository(tmp_path / "lineage.db"),
    )

    assert readiness.status == "not_ready"
    assert readiness.checks["cors"].status == "fail"
