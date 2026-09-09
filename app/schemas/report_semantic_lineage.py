from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.normalized_report_definition import (
    VisualFieldReference,
)


class SemanticLineageObject(BaseModel):
    object_type: Literal[
        "column",
        "measure",
        "hierarchy",
        "hierarchy_level",
    ]
    table_name: str
    object_name: str
    source_path: str | None = None
    hierarchy_name: str | None = None
    level_name: str | None = None


class SemanticLineageCandidate(BaseModel):
    semantic_object: SemanticLineageObject
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    reason: str


class SemanticLineageDiagnosticsSummary(BaseModel):
    status_counts: dict[str, int] = Field(default_factory=dict)
    field_reference_object_type_counts: dict[
        str,
        int,
    ] = Field(default_factory=dict)
    match_counts_by_object_type: dict[
        str,
        dict[str, int],
    ] = Field(default_factory=dict)
    reason_counts: dict[str, int] = Field(default_factory=dict)


class SemanticLineageFieldMatch(BaseModel):
    page_name: str
    page_display_name: str
    visual_id: str
    visual_title: str | None = None
    visual_type: str | None = None

    field_reference: VisualFieldReference

    status: Literal[
        "matched",
        "unmatched",
    ]
    semantic_object: SemanticLineageObject | None = None
    reason: str | None = None
    match_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    candidate_suggestions: list[SemanticLineageCandidate] = Field(default_factory=list)


class ReportSemanticLineageResponse(BaseModel):
    workspace_id: str
    report_id: str
    semantic_model_workspace_id: str
    semantic_model_id: str

    total_field_reference_count: int
    matched_field_reference_count: int
    unmatched_field_reference_count: int

    field_matches: list[SemanticLineageFieldMatch] = Field(default_factory=list)
    diagnostics_summary: SemanticLineageDiagnosticsSummary = Field(
        default_factory=(SemanticLineageDiagnosticsSummary)
    )
    warnings: list[str] = Field(default_factory=list)
