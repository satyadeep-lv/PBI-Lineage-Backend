from typing import Literal

from pydantic import BaseModel, Field


class LineageValidationIssue(BaseModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None


class LineageValidationResponse(BaseModel):
    graph_id: str
    valid: bool
    quality_score: float = Field(ge=0.0, le=100.0)
    issues: list[LineageValidationIssue] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
