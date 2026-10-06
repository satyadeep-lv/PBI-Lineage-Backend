from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from app.api.dependencies.credentials import (
    get_fabric_access_token,
    get_powerbi_access_token,
)
from app.clients.fabric_client import FabricClient
from app.clients.powerbi_client import PowerBIClient
from app.main import app
from app.schemas.app_access import AppAccessCoverage, AppAccessResponse
from app.services.org_app_access_service import OrgAppAccessService
from app.services.workspace_app_access_service import WorkspaceAppAccessService

APP_ID = "0a1b2c3d-0000-4000-8000-000000000001"
WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
ORG_APP_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def override_authentication():
    app.dependency_overrides[get_powerbi_access_token] = lambda: "powerbi-token"
    app.dependency_overrides[get_fabric_access_token] = lambda: "fabric-token"
    yield
    app.dependency_overrides.pop(get_powerbi_access_token, None)
    app.dependency_overrides.pop(get_fabric_access_token, None)


def _response(app_type: str) -> AppAccessResponse:
    return AppAccessResponse(
        app_type=app_type,
        app_id=APP_ID,
        coverage=AppAccessCoverage(
            app_users="complete",
            workspace_members="complete",
            audiences="not_requested",
            audience_members="not_requested",
            audience_content="not_supported",
            objects="complete",
            object_access="complete",
        ),
    )


def test_workspace_app_route_passes_the_power_bi_token_and_options(
    client,
    monkeypatch,
):
    captured = {}

    async def fake_build(self, **kwargs):
        captured.update(kwargs)
        return _response("workspace_app")

    monkeypatch.setattr(WorkspaceAppAccessService, "build", fake_build)

    response = client.get(
        f"/api/v1/apps/{APP_ID}",
        params={"audience_history_days": 7, "include_object_access": "false"},
    )

    assert response.status_code == 200
    assert response.json()["app_type"] == "workspace_app"
    assert captured == {
        "app_id": APP_ID,
        "access_token": "powerbi-token",
        "audience_history_days": 7,
        "include_object_access": False,
    }


def test_audience_history_is_capped_at_the_activity_log_retention(client):
    response = client.get(
        f"/api/v1/apps/{APP_ID}",
        params={"audience_history_days": 29},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"


def test_org_app_route_passes_the_fabric_token_and_options(client, monkeypatch):
    captured = {}

    async def fake_build(self, **kwargs):
        captured.update(kwargs)
        return _response("org_app")

    monkeypatch.setattr(OrgAppAccessService, "build", fake_build)

    response = client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/org-apps/{ORG_APP_ID}",
        params={"include_member_access": "false"},
    )

    assert response.status_code == 200
    assert captured == {
        "workspace_id": WORKSPACE_ID,
        "org_app_id": ORG_APP_ID,
        "access_token": "fabric-token",
        "include_member_access": False,
        "include_object_access": True,
    }


def test_app_routes_require_the_admin_key_when_one_is_configured(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.api.dependencies.security.get_settings",
        lambda: SimpleNamespace(lineage_admin_api_key=SecretStr("expected-key")),
    )

    workspace_app = client.get(f"/api/v1/apps/{APP_ID}")
    org_app = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/org-apps/{ORG_APP_ID}")

    assert workspace_app.status_code == org_app.status_code == 401
    assert workspace_app.json()["error"]["code"] == "LINEAGE_API_KEY_REQUIRED"


def test_app_routes_are_documented_under_apps(client):
    paths = client.get("/openapi.json").json()["paths"]

    for path in (
        "/api/v1/apps/{app_id}",
        "/api/v1/workspaces/{workspace_id}/org-apps/{org_app_id}",
    ):
        operation = paths[path]["get"]
        assert operation["tags"] == ["Apps"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("AppAccessResponse")
        assert "404" in operation["responses"]


@pytest.mark.asyncio
async def test_activity_events_quote_their_window_and_filter(monkeypatch):
    provider_get = AsyncMock(
        return_value=httpx.Response(200, json={"activityEventEntities": []})
    )
    monkeypatch.setattr("app.clients.powerbi_client.provider_get", provider_get)

    await PowerBIClient().get_activity_events(
        access_token="token",
        start_date_time="2026-09-28T00:00:00.000Z",
        end_date_time="2026-09-28T23:59:59.999Z",
        activity="UpdateApp",
    )
    await PowerBIClient().get_activity_events(
        access_token="token",
        start_date_time="ignored",
        end_date_time="ignored",
        activity="UpdateApp",
        continuation_token="abc",
    )

    first, follow_up = (call.kwargs["params"] for call in provider_get.await_args_list)
    assert first == {
        "startDateTime": "'2026-09-28T00:00:00.000Z'",
        "endDateTime": "'2026-09-28T23:59:59.999Z'",
        "$filter": "Activity eq 'UpdateApp'",
    }
    assert follow_up == {"continuationToken": "'abc'"}


@pytest.mark.asyncio
async def test_item_access_details_use_the_fabric_admin_url(monkeypatch):
    provider_get = AsyncMock(return_value=httpx.Response(200, json={}))
    monkeypatch.setattr("app.clients.fabric_client.provider_get", provider_get)

    await FabricClient().list_item_access_details_as_admin(
        workspace_id="ws",
        item_id="item",
        item_type="Report",
        access_token="token",
    )

    call = provider_get.await_args.kwargs
    assert call["url"] == (
        "https://api.fabric.microsoft.com/v1/admin/workspaces/ws/items/item/users"
    )
    assert call["params"] == {"type": "Report"}
