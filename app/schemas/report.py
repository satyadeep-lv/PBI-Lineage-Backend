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

class ReportUser(BaseModel):
    identifier: str
    principal_type: str | None = None
    email_address: str | None = None
    display_name: str | None = None
    user_right: str | None = None


class ReportUserListResponse(BaseModel):
    report_id: str
    users: list[ReportUser]
    count: int
