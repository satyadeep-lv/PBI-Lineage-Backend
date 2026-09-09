from pydantic import BaseModel, Field

from app.schemas.lineage_graph import LineageGraph, LineageNode, LineageNodeType


class LineageSearchResult(BaseModel):
    node: LineageNode
    score: float = Field(ge=0.0, le=1.0)
    matched_fields: list[str] = Field(default_factory=list)


class LineageSearchResponse(BaseModel):
    graph_id: str
    query: str
    results: list[LineageSearchResult] = Field(default_factory=list)
    total: int = 0
    limit: int
    offset: int
    node_types: list[LineageNodeType] = Field(default_factory=list)


class LineageNavigationResponse(BaseModel):
    graph_id: str
    root_node_id: str
    direction: str
    depth: int
    graph: LineageGraph
