from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.dax_dependency import DaxObjectType

PhysicalColumnResolutionMethod = Literal[
    "native_query_select",
    "same_name_assumed",
]


class PhysicalColumnReference(BaseModel):
    source_id: str
    provider: str
    server: str | None = None
    database: str | None = None
    schema_name: str | None = None
    object_name: str | None = None
    column_name: str
    resolution_method: PhysicalColumnResolutionMethod
    fully_qualified_name: str


class SemanticColumnLineageRow(BaseModel):
    semantic_table: str | None = None
    semantic_object_type: DaxObjectType
    semantic_object_name: str
    semantic_dax_expression: str | None = None
    referenced_semantic_table: str | None = None
    referenced_semantic_column: str | None = None
    dependency_depth: int | None = None
    is_direct_dependency: bool | None = None
    physical_columns: list[PhysicalColumnReference] = Field(default_factory=list)


class SemanticColumnLineageWarning(BaseModel):
    code: str
    message: str
    object_name: str | None = None
    source_path: str | None = None


class SemanticModelColumnLineageResponse(BaseModel):
    workspace_id: str
    semantic_model_id: str
    rows: list[SemanticColumnLineageRow] = Field(default_factory=list)
    warnings: list[SemanticColumnLineageWarning] = Field(default_factory=list)
    object_count: int = 0
    row_count: int = 0
