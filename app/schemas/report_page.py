from pydantic import BaseModel, Field


class ReportPage(BaseModel):
    name: str
    display_name: str
    order: int = Field(ge=0)


class ReportPageListResponse(BaseModel):
    workspace_id: str
    report_id: str

    pages: list[ReportPage]

    count: int
