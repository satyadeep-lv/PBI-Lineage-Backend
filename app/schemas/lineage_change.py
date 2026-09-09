from pydantic import BaseModel, Field


class LineageChangeSet(BaseModel):
    graph_id: str
    from_version: int = Field(ge=1)
    to_version: int = Field(ge=1)
    added_node_ids: list[str] = Field(default_factory=list)
    removed_node_ids: list[str] = Field(default_factory=list)
    changed_node_ids: list[str] = Field(default_factory=list)
    added_edge_ids: list[str] = Field(default_factory=list)
    removed_edge_ids: list[str] = Field(default_factory=list)
    changed_edge_ids: list[str] = Field(default_factory=list)
    has_changes: bool = False
