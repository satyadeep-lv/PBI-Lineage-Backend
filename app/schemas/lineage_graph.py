from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.dax_dependency import DaxDependencyAnalysisResponse
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.physical_source import PhysicalSourceDiscoveryResponse
from app.schemas.report_semantic_lineage import ReportSemanticLineageResponse
from app.schemas.snowflake_lineage import SnowflakeLineageSnapshot

LineageNodeType = Literal[
    "workspace",
    "report",
    "report_page",
    "visual",
    "semantic_model",
    "semantic_table",
    "semantic_column",
    "semantic_measure",
    "semantic_hierarchy",
    "semantic_hierarchy_level",
    "query",
    "physical_source",
    "snowflake_object",
]


class LineageNode(BaseModel):
    node_id: str
    node_type: LineageNodeType
    name: str
    qualified_name: str
    workspace_id: str | None = None
    semantic_model_id: str | None = None
    report_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class LineageEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    edge_type: str
    is_lineage: bool = True
    properties: dict[str, Any] = Field(default_factory=dict)


class LineageGraph(BaseModel):
    graph_id: str
    created_at: datetime
    workspace_id: str | None = None
    semantic_model_id: str | None = None
    report_id: str | None = None
    nodes: list[LineageNode] = Field(default_factory=list)
    edges: list[LineageEdge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


class LineageGraphBuildRequest(BaseModel):
    semantic_model: ParsedSemanticModelResponse
    dax_analysis: DaxDependencyAnalysisResponse | None = None
    physical_sources: PhysicalSourceDiscoveryResponse | None = None
    report_lineage: ReportSemanticLineageResponse | None = None
    snowflake_lineage: SnowflakeLineageSnapshot | None = None
