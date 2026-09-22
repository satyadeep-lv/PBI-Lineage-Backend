from pydantic import BaseModel

class Dashboard(BaseModel):
    id: str
    display_name: str | None = None
    is_read_only: bool | None = None
    embed_url: str | None = None

class DashboardListResponse(BaseModel):
    workspace_id: str
    dashboards: list[Dashboard]
    count: int