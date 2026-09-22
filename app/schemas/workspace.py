from pydantic import BaseModel, Field


class Workspace(BaseModel):
    id: str
    name: str

    is_read_only: bool = False
    is_on_dedicated_capacity: bool = False

    capacity_id: str | None = None
    default_dataset_storage_format: str | None = None


class WorkspaceListResponse(BaseModel):
    workspaces: list[Workspace]

    count: int

    top: int = Field(
        ge=1,
    )

    skip: int = Field(
        ge=0,
    )

from pydantic import BaseModel

class WorkspaceUser(BaseModel):
    identifier: str
    principal_type: str | None = None
    email_address: str | None = None
    display_name: str | None = None
    group_user_access_right: str | None = None

class WorkspaceUserListResponse(BaseModel):
    workspace_id: str
    users: list[WorkspaceUser]
    count: int
