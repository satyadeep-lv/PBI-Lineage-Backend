from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ExplorerReportSelection(BaseModel):
    workspace_id: UUID
    report_id: UUID
    semantic_model_id: UUID | None = None
    semantic_model_workspace_id: UUID | None = None
    app_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
    )


class ExplorerRequest(BaseModel):
    reports: list[ExplorerReportSelection] = Field(
        min_length=1,
        max_length=50,
    )
    include_gateway_sources: bool = False
    report_definition_format: Literal[
        "PBIR",
        "PBIR-Legacy",
    ] = "PBIR"
    semantic_model_definition_format: Literal["TMDL"] = "TMDL"

    @model_validator(mode="after")
    def reports_must_be_unique(self) -> "ExplorerRequest":
        report_keys = [
            (selection.workspace_id, selection.report_id) for selection in self.reports
        ]
        if len(report_keys) != len(set(report_keys)):
            raise ValueError("Each workspace/report selection must be unique.")
        return self


class ExplorerWarning(BaseModel):
    code: str
    message: str
    workspace_id: str | None = None
    report_id: str | None = None
    semantic_model_id: str | None = None
    source_path: str | None = None


class ExplorerReportContext(BaseModel):
    workspace_id: str
    workspace_name: str
    report_id: str
    report_name: str
    semantic_model_workspace_id: str | None = None
    semantic_model_id: str | None = None
    app_name: str | None = None


class SourceDatabaseLineageRow(BaseModel):
    workspace_id: str
    workspace_name: str
    report_id: str
    report_name: str
    semantic_model_workspace_id: str
    semantic_model_id: str
    app_name: str | None = None
    semantic_table: str
    query_id: str
    partition_name: str
    source_id: str
    source_kind: str
    source_provider: str
    source_connector: str | None = None
    source_server: str | None = None
    source_database: str | None = None
    source_schema: str | None = None
    source_object_name: str | None = None
    source_object_type: Literal[
        "table",
        "query",
        "file",
        "url",
        "endpoint",
        "unknown",
    ]
    source_fully_qualified_name: str
    gateway_id: str | None = None
    gateway_datasource_id: str | None = None


class SemanticModelObjectRow(BaseModel):
    scope_type: Literal["workspace"] = "workspace"
    workspace_id: str
    workspace_name: str
    report_id: str
    report_name: str
    semantic_model_workspace_id: str
    semantic_model_id: str
    app_name: str | None = None
    semantic_table: str
    semantic_object_type: Literal[
        "table",
        "calculated_table",
        "column",
        "calculated_column",
        "measure",
        "hierarchy",
        "hierarchy_level",
    ]
    semantic_object_name: str
    semantic_data_type: str | None = None
    semantic_source_column: str | None = None
    semantic_dax_expression: str | None = None
    format_string: str | None = None
    is_hidden: bool | None = None
    source_path: str | None = None


class MeasureSourceLineageRow(BaseModel):
    scope_type: Literal["workspace"] = "workspace"
    workspace_id: str
    workspace_name: str
    report_id: str
    report_name: str
    semantic_model_workspace_id: str
    semantic_model_id: str
    app_name: str | None = None
    semantic_table: str | None = None
    semantic_object_type: str
    semantic_object_name: str
    semantic_dax_expression: str | None = None
    source_semantic_table: str | None = None
    source_semantic_object_type: str | None = None
    source_semantic_object_name: str | None = None
    source_column_name: str | None = None
    dependency_depth: int | None = Field(default=None, ge=1)
    is_direct_dependency: bool | None = None
    source_id: str | None = None
    source_provider: str | None = None
    source_server: str | None = None
    source_database: str | None = None
    source_schema: str | None = None
    source_object_name: str | None = None
    source_object_type: str | None = None
    source_fully_qualified_name: str | None = None


class ReportLayoutRow(BaseModel):
    workspace_id: str
    workspace_name: str
    report_id: str
    report_name: str
    semantic_model_id: str | None = None
    app_name: str | None = None
    metadata_source: Literal["fabric_report_definition"] = "fabric_report_definition"
    report_definition_format: str
    definition_part_count: int = Field(ge=0)
    page_id: str
    page_name: str
    page_order: int | None = None
    visual_id: str
    visual_name: str
    visual_type: str | None = None
    field_usage: str | None = None
    field_role: str | None = None
    field_type: str | None = None
    table_name: str | None = None
    column_measure_name: str | None = None
    aggregation: int | str | None = None
    query_reference: str | None = None
    visual_x: float | None = None
    visual_y: float | None = None
    visual_width: float | None = None
    visual_height: float | None = None


class VisualSourceLookupRow(BaseModel):
    workspace_id: str
    workspace_name: str
    report_id: str
    report_name: str
    semantic_model_workspace_id: str
    semantic_model_id: str
    app_name: str | None = None
    page_id: str
    page_name: str
    visual_id: str
    visual_name: str
    visual_type: str | None = None
    field_usage: str
    field_role: str | None = None
    field_type: str
    visual_table_name: str | None = None
    visual_field_name: str | None = None
    aggregation: int | str | None = None
    query_reference: str | None = None
    semantic_table: str | None = None
    semantic_object_name: str | None = None
    semantic_object_type: str | None = None
    semantic_object_source_path: str | None = None
    match_status: Literal["matched", "unmatched"]
    match_confidence: float = Field(ge=0.0, le=1.0)
    match_reason: str | None = None
    visual_x: float | None = None
    visual_y: float | None = None
    visual_width: float | None = None
    visual_height: float | None = None


class SourceDatabaseLineageDataset(BaseModel):
    rows: list[SourceDatabaseLineageRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class SemanticModelObjectsDataset(BaseModel):
    rows: list[SemanticModelObjectRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class MeasureSourceLineageDataset(BaseModel):
    rows: list[MeasureSourceLineageRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class ReportLayoutDataset(BaseModel):
    rows: list[ReportLayoutRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class VisualSourceLookupDataset(BaseModel):
    rows: list[VisualSourceLookupRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class ExplorerResponseBase(BaseModel):
    generated_at: datetime
    reports: list[ExplorerReportContext] = Field(default_factory=list)
    report_count: int = Field(default=0, ge=0)
    semantic_model_count: int = Field(default=0, ge=0)
    warnings: list[ExplorerWarning] = Field(default_factory=list)


class SourceDatabaseLineageResponse(ExplorerResponseBase):
    rows: list[SourceDatabaseLineageRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class SemanticModelObjectsResponse(ExplorerResponseBase):
    rows: list[SemanticModelObjectRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class MeasureSourceLineageResponse(ExplorerResponseBase):
    rows: list[MeasureSourceLineageRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class ReportLayoutResponse(ExplorerResponseBase):
    rows: list[ReportLayoutRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class VisualSourceLookupResponse(ExplorerResponseBase):
    rows: list[VisualSourceLookupRow] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class ExplorerSnapshotResponse(ExplorerResponseBase):
    source_database_lineage: SourceDatabaseLineageDataset
    semantic_model_objects: SemanticModelObjectsDataset
    measure_source_lineage: MeasureSourceLineageDataset
    report_layout: ReportLayoutDataset
    visual_source_lookup: VisualSourceLookupDataset
