from datetime import UTC, datetime

import pytest

from app.api.dependencies.credentials import get_powerbi_access_token
from app.main import app
from app.schemas.scanner import (
    ScannerModifiedWorkspacesResponse,
    ScannerResultResponse,
    ScannerResultSummary,
    ScannerScanResponse,
)
from app.services.scanner_service import ScannerService

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
SCAN_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def override_authentication():
    async def fake_powerbi_token() -> str:
        return "fake-test-token"

    app.dependency_overrides[get_powerbi_access_token] = fake_powerbi_token
    yield
    app.dependency_overrides.pop(get_powerbi_access_token, None)


def test_list_scanner_workspaces(client, monkeypatch):
    async def fake_list(self, **kwargs):
        assert kwargs["access_token"] == "fake-test-token"
        assert kwargs["modified_since"] == datetime(
            2026,
            9,
            1,
            tzinfo=UTC,
        )
        return ScannerModifiedWorkspacesResponse(
            workspaces=[WORKSPACE_ID],
            count=1,
        )

    monkeypatch.setattr(
        ScannerService,
        "list_modified_workspaces",
        fake_list,
    )

    response = client.get(
        "/api/v1/scanner/workspaces/modified",
        params={"modified_since": "2026-09-01T00:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json()["workspaces"] == [WORKSPACE_ID]


def test_start_scanner_scan(client, monkeypatch):
    async def fake_start(self, *, access_token, request):
        assert access_token == "fake-test-token"
        assert str(request.workspaces[0]) == WORKSPACE_ID
        assert request.dataset_expressions is True
        return ScannerScanResponse(
            scan_id=SCAN_ID,
            created_at="2026-09-02T10:00:00Z",
            status="NotStarted",
        )

    monkeypatch.setattr(ScannerService, "start_scan", fake_start)

    response = client.post(
        "/api/v1/scanner/workspaces/scan",
        json={"workspaces": [WORKSPACE_ID]},
    )

    assert response.status_code == 202
    assert response.json()["scan_id"] == SCAN_ID


def test_get_scanner_scan_status(client, monkeypatch):
    async def fake_status(self, **kwargs):
        assert kwargs["scan_id"] == SCAN_ID
        return ScannerScanResponse(
            scan_id=SCAN_ID,
            created_at="2026-09-02T10:00:00Z",
            status="Succeeded",
        )

    monkeypatch.setattr(ScannerService, "get_scan_status", fake_status)

    response = client.get(f"/api/v1/scanner/scans/{SCAN_ID}/status")

    assert response.status_code == 200
    assert response.json()["status"] == "Succeeded"


def test_get_scanner_result_returns_summary_and_raw_payload(
    client,
    monkeypatch,
):
    async def fake_result(self, **kwargs):
        assert kwargs["scan_id"] == SCAN_ID
        return ScannerResultResponse(
            scan_id=SCAN_ID,
            sections=["workspaces"],
            summary=ScannerResultSummary(workspace_count=1),
            payload={"workspaces": [{"id": WORKSPACE_ID}]},
        )

    monkeypatch.setattr(ScannerService, "get_scan_result", fake_result)

    response = client.get(f"/api/v1/scanner/scans/{SCAN_ID}/result")

    assert response.status_code == 200
    assert response.json()["summary"]["workspace_count"] == 1
    assert response.json()["payload"]["workspaces"][0]["id"] == (WORKSPACE_ID)
