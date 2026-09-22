from typing import Any

from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import UpstreamInvalidResponseError
from app.schemas.workspace import (
    Workspace,
    WorkspaceListResponse,
    WorkspaceUserListResponse,
    WorkspaceUser
)
from app.schemas.dashboard import (
    Dashboard,
    DashboardListResponse
)


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

        workspaces = [self._map_workspace(item) for item in raw_workspaces]

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

    async def list_workspace_users(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> WorkspaceUserListResponse:  # Make sure to import this at the top
        raw_users = await self.client.get_workspace_users(
            workspace_id=workspace_id,
            access_token=access_token,
        )

        users = [
            WorkspaceUser(
                identifier=u.get("identifier"),
                principal_type=u.get("principalType"),
                email_address=u.get("emailAddress"),
                display_name=u.get("displayName"),
                group_user_access_right=u.get("groupUserAccessRight"),
            )
            for u in raw_users if u.get("identifier")
        ]

        return WorkspaceUserListResponse(
            workspace_id=workspace_id,
            users=users,
            count=len(users),
        )

    async def list_dashboards(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> DashboardListResponse: # Make sure to import this at the top
        raw_dashboards = await self.client.get_dashboards_in_workspace(
            workspace_id=workspace_id,
            access_token=access_token,
        )

        dashboards = [
            Dashboard(
                id=d.get("id"),
                display_name=d.get("displayName"),
                is_read_only=d.get("isReadOnly"),
                embed_url=d.get("embedUrl"),
            )
            for d in raw_dashboards if d.get("id")
        ]

        return DashboardListResponse(
            workspace_id=workspace_id,
            dashboards=dashboards,
            count=len(dashboards),
        )
    async def get_filtered_workspace_inventory(
        self,
        *,
        access_token: str,
    ) -> WorkspaceListResponse:
        
        # We can reuse your existing client.get_workspaces method
        raw_workspaces = await self.client.get_workspaces(
            access_token=access_token,
            top=1000,  # Grabbing a large chunk to mimic the Streamlit behavior
            skip=0,
        )

        # Assuming your WorkspaceService already has a _map_workspace method (since get_workspace exists)
        workspaces = [self._map_workspace(ws) for ws in raw_workspaces]

        # --- MIGRATE YOUR STREAMLIT FILTERING LOGIC HERE ---
        # For example, if you were excluding by name:
        # excluded_names = ["Test Workspace", "Personal Workspace"]
        # filtered_workspaces = [ws for ws in workspaces if ws.name not in excluded_names]
        
        # If you don't want to filter yet, just return them all:
        filtered_workspaces = workspaces 

        return WorkspaceListResponse(
            workspaces=filtered_workspaces,
            count=len(filtered_workspaces),
            top=1000,
            skip=0,
        )