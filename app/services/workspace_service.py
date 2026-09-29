from typing import Any

from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import UpstreamInvalidResponseError
from app.schemas.workspace import (
    Workspace,
    WorkspaceListResponse,
)

# Power BI provisions these workspaces itself and their semantic models are
# not readable through the Fabric definition APIs, so every lineage call
# against them fails upstream. They are noise in a lineage picker.
SYSTEM_WORKSPACE_TYPES = frozenset({"admininsights"})


class WorkspaceService:
    def __init__(self) -> None:
        self.client = PowerBIClient()

    async def list_workspaces(
        self,
        *,
        access_token: str,
        top: int,
        skip: int,
    ) -> WorkspaceListResponse:
        raw_workspaces = await self.client.get_workspaces(
            access_token=access_token,
            top=top,
            skip=skip,
        )

        workspaces = [
            workspace
            for workspace in (self._map_workspace(item) for item in raw_workspaces)
            if not self.is_system_workspace(workspace)
        ]

        return WorkspaceListResponse(
            workspaces=workspaces,
            count=len(workspaces),
            top=top,
            skip=skip,
        )

    async def get_workspace(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> Workspace:
        raw_workspace = await self.client.get_workspace(
            workspace_id=workspace_id,
            access_token=access_token,
        )

        return self._map_workspace(raw_workspace)

    @staticmethod
    def is_system_workspace(workspace: Workspace) -> bool:
        return (workspace.type or "").casefold() in SYSTEM_WORKSPACE_TYPES

    @staticmethod
    def _map_workspace(
        workspace: dict[str, Any],
    ) -> Workspace:
        workspace_id = workspace.get("id")
        workspace_name = workspace.get("name")

        if not isinstance(workspace_id, str) or not workspace_id:
            raise UpstreamInvalidResponseError("powerbi")

        if not isinstance(workspace_name, str) or not workspace_name:
            raise UpstreamInvalidResponseError("powerbi")

        return Workspace(
            id=workspace_id,
            name=workspace_name,
            type=workspace.get("type"),
            is_read_only=bool(
                workspace.get(
                    "isReadOnly",
                    False,
                )
            ),
            is_on_dedicated_capacity=bool(
                workspace.get(
                    "isOnDedicatedCapacity",
                    False,
                )
            ),
            capacity_id=workspace.get("capacityId"),
            default_dataset_storage_format=(
                workspace.get("defaultDatasetStorageFormat")
            ),
        )
