from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.lineage_graph import LineageGraph
from app.schemas.report import Report
from app.schemas.semantic_model import SemanticModel
from app.schemas.workspace import Workspace


class EstateReportBinding(BaseModel):
    report_id: str
    semantic_model_id: str | None = None
    status: Literal["matched", "unresolved"]


class EstateWorkspaceInventory(BaseModel):
    workspace: Workspace
    reports: list[Report] = Field(default_factory=list)
    semantic_models: list[SemanticModel] = Field(default_factory=list)
    report_bindings: list[EstateReportBinding] = Field(default_factory=list)


class EstateDiscoveryWarning(BaseModel):
    code: str
    message: str
    workspace_id: str | None = None
    resource_type: str | None = None


class EstateDiscoveryResponse(BaseModel):
    workspaces: list[EstateWorkspaceInventory] = Field(default_factory=list)
    graph: LineageGraph
    warnings: list[EstateDiscoveryWarning] = Field(default_factory=list)
    workspace_count: int = 0
    report_count: int = 0
    semantic_model_count: int = 0
