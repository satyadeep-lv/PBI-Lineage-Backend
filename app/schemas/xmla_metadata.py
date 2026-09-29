from typing import Literal

from pydantic import BaseModel, Field


class XmlaMetadataWarning(BaseModel):
    code: str
    message: str
    object_name: str | None = None


class XmlaSemanticModelColumn(BaseModel):
    name: str
    data_type: str | None = None
    source_column: str | None = None
    expression: str | None = None
    format_string: str | None = None
    summarize_by: str | None = None
    sort_by_column: str | None = None
    is_hidden: bool | None = None
    description: str | None = None
    lineage_tag: str | None = None
    source_lineage_tag: str | None = None


class XmlaSemanticModelMeasure(BaseModel):
    name: str
    expression: str | None = None
    format_string: str | None = None
    is_hidden: bool | None = None
    description: str | None = None
    lineage_tag: str | None = None


class XmlaSemanticModelPartition(BaseModel):
    name: str
    mode: str | None = None
    source_type: str | None = None
    expression: str | None = None
    is_refreshable: bool | None = None


class XmlaSemanticModelHierarchyLevel(BaseModel):
    name: str
    column: str | None = None
    ordinal: int | None = None


class XmlaSemanticModelHierarchy(BaseModel):
    name: str
    is_hidden: bool | None = None
    levels: list[XmlaSemanticModelHierarchyLevel] = Field(default_factory=list)


class XmlaSemanticModelTable(BaseModel):
    name: str
    description: str | None = None
    is_hidden: bool | None = None
    columns: list[XmlaSemanticModelColumn] = Field(default_factory=list)
    measures: list[XmlaSemanticModelMeasure] = Field(default_factory=list)
    partitions: list[XmlaSemanticModelPartition] = Field(default_factory=list)
    hierarchies: list[XmlaSemanticModelHierarchy] = Field(default_factory=list)


class XmlaSemanticModelRelationship(BaseModel):
    name: str | None = None
    from_table: str | None = None
    from_column: str | None = None
    to_table: str | None = None
    to_column: str | None = None
    is_active: bool | None = None
    cardinality: str | None = None
    cross_filter_direction: str | None = None
    security_filtering_behavior: str | None = None


class XmlaCalcDependency(BaseModel):
    """One row of the engine-computed ``DISCOVER_CALC_DEPENDENCY`` DMV.

    Authoritative: this is Microsoft's own dependency graph, not a
    text-parsed guess, so it covers every ``object_type`` the DMV reports
    (``MEASURE``, ``CALC_COLUMN``, ``CALC_TABLE``, relationship/RLS rows,
    etc.) — callers filter to the object types they care about.
    """

    object_type: str | None = None
    table: str | None = None
    object: str | None = None
    expression: str | None = None
    referenced_object_type: str
    referenced_table: str | None = None
    referenced_object: str | None = None
    referenced_expression: str | None = None


class XmlaSemanticModelMetadataResponse(BaseModel):
    workspace_id: str
    semantic_model_id: str
    source: Literal["xmla"] = "xmla"
    xmla_endpoint: str
    database_name: str | None = None

    table_count: int
    column_count: int
    measure_count: int
    relationship_count: int
    hierarchy_count: int
    partition_count: int

    tables: list[XmlaSemanticModelTable] = Field(default_factory=list)
    relationships: list[XmlaSemanticModelRelationship] = Field(default_factory=list)
    calc_dependencies: list[XmlaCalcDependency] = Field(default_factory=list)
    warnings: list[XmlaMetadataWarning] = Field(default_factory=list)
