from typing import Literal

from pydantic import BaseModel, Field


class VisualFieldReference(BaseModel):
    object_type: Literal[
        "column",
        "measure",
        "hierarchy",
        "hierarchy_level",
    ]

    table_name: str | None = None
    object_name: str | None = None

    # Where/how the field is used in the visual
    usage: Literal[
        "projection",
        "sort",
        "filter",
    ]

    # Power BI visual role, for example:
    # Category, Series, Y, X, Values, Rows, Columns, Tooltips
    role: str | None = None

    # Diagnostic metadata only.
    # Do NOT use this as authoritative table/field identity.
    query_ref: str | None = None

    active: bool | None = None

    # Used for hierarchy references
    hierarchy_name: str | None = None
    level_name: str | None = None

    # Preserve the PBIR aggregation function value.
    # Don't translate the numeric value yet.
    aggregation_function: int | str | None = None


class SemanticModelReference(BaseModel):
    mode: Literal[
        "by_connection",
        "by_path",
        "unknown",
    ]

    semantic_model_id: str | None = None
    path: str | None = None


class NormalizedVisualPosition(BaseModel):
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    z: float | None = None
    tab_order: float | None = None


class NormalizedReportVisual(BaseModel):
    id: str

    internal_name: str

    title: str | None = None
    title_visible: bool | None = None
    title_is_dynamic: bool = False

    visual_type: str | None = None

    parent_group_name: str | None = None
    is_hidden: bool = False

    has_query: bool = False

    position: NormalizedVisualPosition | None = None

    field_references: list[VisualFieldReference] = Field(default_factory=list)


class NormalizedReportPage(BaseModel):
    name: str
    display_name: str

    order: int | None = None
    is_active: bool = False

    display_option: str | None = None

    width: float | None = None
    height: float | None = None

    visuals: list[NormalizedReportVisual]

    visual_count: int


class NormalizedReportDefinitionResponse(BaseModel):
    workspace_id: str
    report_id: str

    format: Literal[
        "PBIR",
        "PBIR-Legacy",
        "Unknown",
    ]

    definition_version: str | None = None

    semantic_model: SemanticModelReference | None = None

    pages: list[NormalizedReportPage]

    page_count: int
    visual_count: int

    source_part_count: int
    decoded_json_part_count: int

    warnings: list[str]
