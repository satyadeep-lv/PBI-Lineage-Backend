from pydantic import BaseModel


class Report(BaseModel):
    id: str
    name: str

    dataset_id: str | None = None
    description: str | None = None

    report_type: str | None = None
    format: str | None = None

    web_url: str | None = None

    is_owned_by_me: bool | None = None


class ReportListResponse(BaseModel):
    workspace_id: str

    reports: list[Report]

    count: int
