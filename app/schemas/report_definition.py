from pydantic import BaseModel


class ReportDefinitionPart(BaseModel):
    path: str
    payload: str
    payload_type: str


class ReportDefinition(BaseModel):
    format: str | None = None
    parts: list[ReportDefinitionPart]


class ReportDefinitionResponse(BaseModel):
    workspace_id: str
    report_id: str
    definition: ReportDefinition
