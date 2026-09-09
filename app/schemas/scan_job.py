from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.lineage_graph import LineageGraphBuildRequest
from app.schemas.lineage_persistence import GraphVersionMetadata

ScanJobStatus = Literal["queued", "running", "succeeded", "failed"]


class LineageScanJobRequest(BaseModel):
    graph: LineageGraphBuildRequest


class LiveLineageScanRequest(BaseModel):
    semantic_model_workspace_id: str
    semantic_model_id: str
    report_workspace_id: str | None = None
    report_id: str | None = None
    include_gateway_sources: bool = True
    report_definition_format: Literal["PBIR", "PBIR-Legacy"] = "PBIR"


class LineageScanJob(BaseModel):
    job_id: str
    status: ScanJobStatus
    created_at: datetime
    updated_at: datetime
    result: GraphVersionMetadata | None = None
    error_code: str | None = None
    error_message: str | None = None
