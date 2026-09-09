from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.lineage_graph import LineageGraph


class GraphVersionMetadata(BaseModel):
    graph_id: str
    version: int = Field(ge=1)
    content_hash: str
    created_at: datetime


class StoredLineageGraph(BaseModel):
    graph: LineageGraph
    metadata: GraphVersionMetadata
    created_new_version: bool


class GraphVersionListResponse(BaseModel):
    graph_id: str
    versions: list[GraphVersionMetadata] = Field(default_factory=list)
    count: int = 0
