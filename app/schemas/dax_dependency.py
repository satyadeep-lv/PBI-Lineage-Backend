from typing import Literal

from pydantic import BaseModel, Field

DaxObjectType = Literal[
    "measure",
    "calculated_column",
    "calculated_table",
    "column",
    "table",
    "unresolved",
]


class DaxObjectReference(BaseModel):
    object_type: DaxObjectType
    table_name: str | None = None
    object_name: str
    qualified_name: str


class DaxDependencyEdge(BaseModel):
    source: DaxObjectReference
    target: DaxObjectReference
    reference_text: str


class DaxDependencyCycle(BaseModel):
    members: list[str] = Field(min_length=1)


class DaxDependencyWarning(BaseModel):
    code: str
    message: str
    object_name: str | None = None
    reference_text: str | None = None


class DaxDependencyAnalysisResponse(BaseModel):
    workspace_id: str
    semantic_model_id: str
    objects: list[DaxObjectReference] = Field(default_factory=list)
    dependencies: list[DaxDependencyEdge] = Field(default_factory=list)
    cycles: list[DaxDependencyCycle] = Field(default_factory=list)
    warnings: list[DaxDependencyWarning] = Field(default_factory=list)

    object_count: int = 0
    dependency_count: int = 0
    cycle_count: int = 0
