import pytest

from app.services.workspace_service import WorkspaceService


class _PowerBIClient:
    def __init__(self, raw_workspaces):
        self.raw_workspaces = raw_workspaces

    async def get_workspaces(self, *, access_token, top, skip):
        return self.raw_workspaces


@pytest.mark.asyncio
async def test_list_workspaces_excludes_power_bi_system_workspaces():
    service = WorkspaceService()
    service.client = _PowerBIClient(
        [
            {"id": "11111111-1111-1111-1111-111111111111", "name": "POC"},
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "Admin monitoring",
                "type": "AdminInsights",
            },
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "name": "DEV",
                "type": "Workspace",
            },
        ]
    )

    result = await service.list_workspaces(
        access_token="token",
        top=100,
        skip=0,
    )

    assert [workspace.name for workspace in result.workspaces] == ["POC", "DEV"]
    assert result.count == 2
    assert result.workspaces[1].type == "Workspace"
