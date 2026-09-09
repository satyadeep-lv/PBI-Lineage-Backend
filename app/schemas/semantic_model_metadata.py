from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelResponse,
)
from app.schemas.xmla_metadata import (
    XmlaSemanticModelMetadataResponse,
)


class SemanticModelMetadataMatch(BaseModel):
    object_type: Literal[
        "table",
        "column",
        "measure",
        "hierarchy",
        "hierarchy_level",
        "partition",
        "relationship",
    ]
    object_name: str
    table_name: str | None = None
    status: Literal[
        "matched",
        "definition_only",
        "xmla_only",
    ]
    definition_source_path: str | None = None
    xmla_object_name: str | None = None


class SemanticModelMetadataReconciliation(BaseModel):
    matched_count: int
    definition_only_count: int
    xmla_only_count: int
    matches: list[SemanticModelMetadataMatch] = Field(default_factory=list)


class SemanticModelMetadataResponse(BaseModel):
    workspace_id: str
    semantic_model_id: str
    definition: ParsedSemanticModelResponse
    xmla: XmlaSemanticModelMetadataResponse
    reconciliation: SemanticModelMetadataReconciliation
