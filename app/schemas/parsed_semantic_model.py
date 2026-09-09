from pydantic import BaseModel, Field


class ParsedSemanticModelWarning(BaseModel):
    code: str
    message: str
    path: str | None = None


class ParsedSemanticModelColumn(BaseModel):
    name: str
    source_path: str | None = None
    data_type: str | None = None
    source_column: str | None = None
    expression: str | None = None
    is_hidden: bool | None = None


class ParsedSemanticModelMeasure(BaseModel):
    name: str
    source_path: str | None = None
    expression: str | None = None
    format_string: str | None = None
    is_hidden: bool | None = None


class ParsedSemanticModelRelationship(BaseModel):
    name: str | None = None
    source_path: str | None = None
    from_table: str | None = None
    from_column: str | None = None
    to_table: str | None = None
    to_column: str | None = None
    is_active: bool | None = None
    cardinality: str | None = None
    cross_filter_direction: str | None = None


class ParsedSemanticModelHierarchyLevel(BaseModel):
    name: str
    source_path: str | None = None
    column: str | None = None


class ParsedSemanticModelHierarchy(BaseModel):
    name: str
    source_path: str | None = None
    levels: list[ParsedSemanticModelHierarchyLevel] = Field(default_factory=list)


class ParsedSemanticModelPartition(BaseModel):
    name: str
    source_path: str | None = None
    mode: str | None = None
    source_type: str | None = None
    expression: str | None = None


class ParsedSemanticModelTable(BaseModel):
    name: str
    source_path: str | None = None
    expression: str | None = None
    columns: list[ParsedSemanticModelColumn] = Field(default_factory=list)
    measures: list[ParsedSemanticModelMeasure] = Field(default_factory=list)
    hierarchies: list[ParsedSemanticModelHierarchy] = Field(default_factory=list)
    partitions: list[ParsedSemanticModelPartition] = Field(default_factory=list)


class ParsedSemanticModelResponse(BaseModel):
    workspace_id: str
    semantic_model_id: str
    format: str | None = None
    tables: list[ParsedSemanticModelTable] = Field(default_factory=list)
    relationships: list[ParsedSemanticModelRelationship] = Field(default_factory=list)
    warnings: list[ParsedSemanticModelWarning] = Field(default_factory=list)
