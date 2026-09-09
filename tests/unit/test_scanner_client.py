from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients.powerbi_client import PowerBIClient


@pytest.mark.asyncio
async def test_get_modified_workspaces_uses_admin_endpoint(monkeypatch):
    provider_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json=[{"id": "11111111-1111-1111-1111-111111111111"}],
        )
    )
    monkeypatch.setattr(
        "app.clients.powerbi_client.provider_get",
        provider_get,
    )

    result = await PowerBIClient().get_modified_workspaces(
        access_token="token",
        modified_since="2026-09-01T00:00:00Z",
        exclude_personal_workspaces=True,
        exclude_inactive_workspaces=True,
    )

    assert len(result) == 1
    provider_get.assert_awaited_once_with(
        provider="powerbi",
        url=("https://api.powerbi.com/v1.0/myorg/admin/workspaces/modified"),
        access_token="token",
        params={
            "excludePersonalWorkspaces": True,
            "excludeInActiveWorkspaces": True,
            "modifiedSince": "2026-09-01T00:00:00Z",
        },
    )


@pytest.mark.asyncio
async def test_start_workspace_scan_forwards_all_scan_options(monkeypatch):
    provider_post = AsyncMock(
        return_value=httpx.Response(
            202,
            json={
                "id": "22222222-2222-2222-2222-222222222222",
                "createdDateTime": "2026-09-02T10:00:00Z",
                "status": "NotStarted",
            },
        )
    )
    monkeypatch.setattr(
        "app.clients.powerbi_client.provider_post",
        provider_post,
    )

    await PowerBIClient().start_workspace_scan(
        access_token="token",
        workspace_ids=["11111111-1111-1111-1111-111111111111"],
        lineage=True,
        datasource_details=True,
        dataset_schema=True,
        dataset_expressions=True,
        get_artifact_users=False,
    )

    provider_post.assert_awaited_once_with(
        provider="powerbi",
        url=("https://api.powerbi.com/v1.0/myorg/admin/workspaces/getInfo"),
        access_token="token",
        params={
            "lineage": True,
            "datasourceDetails": True,
            "datasetSchema": True,
            "datasetExpressions": True,
            "getArtifactUsers": False,
        },
        json_body={"workspaces": ["11111111-1111-1111-1111-111111111111"]},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "path"),
    [
        ("get_workspace_scan_status", "scanStatus"),
        ("get_workspace_scan_result", "scanResult"),
    ],
)
async def test_scan_reads_use_scan_id_endpoint(
    monkeypatch,
    method_name,
    path,
):
    provider_get = AsyncMock(return_value=httpx.Response(200, json={}))
    monkeypatch.setattr(
        "app.clients.powerbi_client.provider_get",
        provider_get,
    )
    scan_id = "22222222-2222-2222-2222-222222222222"

    await getattr(PowerBIClient(), method_name)(
        access_token="token",
        scan_id=scan_id,
    )

    provider_get.assert_awaited_once_with(
        provider="powerbi",
        url=(f"https://api.powerbi.com/v1.0/myorg/admin/workspaces/{path}/{scan_id}"),
        access_token="token",
        not_found_resource="scanner scan",
    )
