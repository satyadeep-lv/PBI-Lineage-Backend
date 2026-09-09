from pydantic import BaseModel, Field

from app.schemas.lineage_graph import LineageNode


class ImpactedNode(BaseModel):
    node: LineageNode
    distance: int = Field(ge=1)
    path_node_ids: list[str] = Field(min_length=2)
    path_edge_ids: list[str] = Field(min_length=1)


class ImpactAnalysisResponse(BaseModel):
    graph_id: str
    source_node: LineageNode
    direction: str = "downstream"
    max_depth: int
    impacted_nodes: list[ImpactedNode] = Field(default_factory=list)
    impacted_count: int = 0
    truncated: bool = False
