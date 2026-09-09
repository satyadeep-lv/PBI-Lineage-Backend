from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ScannerWorkspaceScanRequest(BaseModel):
    workspaces: list[UUID] = Field(
        min_length=1,
        max_length=100,
    )
    lineage: bool = True
    datasource_details: bool = True
    dataset_schema: bool = True
    dataset_expressions: bool = True
    get_artifact_users: bool = False


class ScannerErrorDetail(BaseModel):
    code: str | None = None
    message: str | None = None
    target: str | None = None


class ScannerScanResponse(BaseModel):
    scan_id: UUID
    created_at: datetime
    status: str
    error: ScannerErrorDetail | None = None


class ScannerModifiedWorkspacesResponse(BaseModel):
    workspaces: list[UUID]
    count: int


class ScannerResultSummary(BaseModel):
    workspace_count: int = 0
    report_count: int = 0
    dashboard_count: int = 0
    semantic_model_count: int = 0
    dataflow_count: int = 0
    datamart_count: int = 0
    table_count: int = 0
    column_count: int = 0
    measure_count: int = 0
    relationship_count: int = 0
    role_count: int = 0
    dataset_expression_count: int = 0
    table_source_expression_count: int = 0
    datasource_instance_count: int = 0
    misconfigured_datasource_instance_count: int = 0


class ScannerResultResponse(BaseModel):
    scan_id: UUID
    sections: list[str]
    summary: ScannerResultSummary
    payload: dict[str, Any]
