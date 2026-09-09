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
