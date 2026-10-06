from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SnowflakeObjectReference(BaseModel):
    object_id: str
    database: str
    schema_name: str
    object_name: str
    object_domain: str
    qualified_name: str
    column_name: str | None = None
    status: str | None = None
    # The container's real kind (TABLE, VIEW, MATERIALIZED VIEW, DYNAMIC
    # TABLE, EXTERNAL TABLE ...). `object_domain` is GET_LINEAGE's coarse
    # domain, which reports every table-like object -- views included -- as
    # TABLE.
    object_type: str | None = None


class SnowflakeDependency(BaseModel):
    source: SnowflakeObjectReference
    target: SnowflakeObjectReference
    dependency_type: str
    distance: int | None = None
    process: dict[str, Any] | list[Any] | str | None = None


class SnowflakeLineageWarning(BaseModel):
    code: str
    message: str
    row_index: int | None = None
    root_object_name: str | None = None


class SnowflakeLineageSnapshot(BaseModel):
    account_identifier: str
    objects: list[SnowflakeObjectReference] = Field(default_factory=list)
    dependencies: list[SnowflakeDependency] = Field(default_factory=list)
    warnings: list[SnowflakeLineageWarning] = Field(default_factory=list)
    object_count: int = 0
    dependency_count: int = 0


class SnowflakeLineageRowsRequest(BaseModel):
    account_identifier: str
    rows: list[dict[str, object]] = Field(default_factory=list)


class SnowflakeLineageDiscoveryRequest(BaseModel):
    account_identifier: str
    warehouse: str | None = None
    role: str | None = None
    token_type: Literal[
        "OAUTH",
        "KEYPAIR_JWT",
        "PROGRAMMATIC_ACCESS_TOKEN",
    ] = "OAUTH"


class SnowflakeDeepLineageRequest(BaseModel):
    object_name: str = Field(min_length=5, max_length=1024)
    column_name: str | None = Field(default=None, min_length=1, max_length=255)
    object_domain: Literal["TABLE", "COLUMN"] | None = None
    direction: Literal["UPSTREAM", "DOWNSTREAM"] = "UPSTREAM"
    max_depth: int = Field(default=50, ge=1, le=100)
    max_concurrency: int = Field(default=8, ge=1, le=32)
    max_nodes: int = Field(default=5000, ge=1, le=50000)
    max_edges: int = Field(default=10000, ge=1, le=100000)
    max_queries: int = Field(default=2000, ge=1, le=10000)
    include_process: bool = True
    # Read each traced object's defining SQL (view DDL, or the statement that
    # last loaded a table) and report every column's transformation.
    include_transformations: bool = True
    # When GET_LINEAGE has nothing for a column, read the SQL that defines it
    # and follow the columns it selects from. Inferred edges carry
    # dependency_type SQL_INFERRED. Upstream traces only.
    infer_missing_lineage: bool = True
    # Table loads are first looked for in INFORMATION_SCHEMA.QUERY_HISTORY: the
    # last 7 days, and only statements this role may see (its own, or on
    # warehouses it can MONITOR/OPERATE). Loads run by other users, or older,
    # need SNOWFLAKE.ACCOUNT_USAGE (ACCESS_HISTORY and QUERY_HISTORY), which
    # needs the GOVERNANCE_VIEWER database role or IMPORTED PRIVILEGES on the
    # SNOWFLAKE database, and lags by up to 3 hours.
    search_account_usage: bool = True
    history_lookback_days: int = Field(default=365, ge=1, le=365)

    @model_validator(mode="after")
    def infer_and_validate_domain(self) -> "SnowflakeDeepLineageRequest":
        inferred_domain = "COLUMN" if self.column_name else "TABLE"
        if self.object_domain is not None and self.object_domain != inferred_domain:
            raise ValueError(
                "object_domain must be COLUMN when column_name is supplied and "
                "TABLE when it is omitted."
            )
        if any(ord(character) < 32 for character in self.object_name):
            raise ValueError("object_name cannot contain control characters.")
        self.object_domain = inferred_domain
        return self


SnowflakeTransformationKind = Literal[
    # The column is computed by an expression.
    "EXPRESSION",
    # Copied, possibly renamed, from an upstream column.
    "PASS_THROUGH",
    # Selected by its own name, unchanged.
    "DIRECT_REFERENCE",
    # Loaded by COPY INTO straight from staged files.
    "STAGE_LOAD",
    # The table is a clone; its columns are the clone source's.
    "CLONE",
    # The loading statement was found but does not name this column; the
    # transformation shows the statement's select list instead.
    "INGESTION_QUERY",
    # A table column with no loading statement in the searched history.
    "BASE_COLUMN",
    # The defining SQL was read but does not produce this column.
    "NOT_FOUND",
    # No defining SQL could be read at all.
    "NO_DEFINITION",
    # An object-level node of a table trace; there is no column to describe.
    "OBJECT",
]

SnowflakeDefinitionSource = Literal[
    # The object's own definition (SHOW VIEWS / SHOW DYNAMIC TABLES text, or
    # GET_DDL): views, materialized views, dynamic and external tables.
    "OBJECT_DDL",
    # The statement GET_LINEAGE named as the process behind an edge.
    "LINEAGE_PROCESS",
    # INFORMATION_SCHEMA.QUERY_HISTORY: the last 7 days.
    "QUERY_HISTORY",
    # SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY, which records each write's real
    # target, joined to ACCOUNT_USAGE.QUERY_HISTORY for the text.
    "ACCESS_HISTORY",
    # A text search of SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY, used when
    # ACCESS_HISTORY cannot be read.
    "ACCOUNT_USAGE_QUERY_HISTORY",
]


class SnowflakeColumnTransformation(BaseModel):
    """How one traced object or column is produced.

    One entry per node of the trace, the starting object included at level 0,
    so it carries the same information as the legacy TRACE_COLUMN_LINEAGE
    procedure's COLUMN_TRANSFORMATION / MODIFICATION_SQL columns without
    repeating a node once per parent.
    """

    object_id: str
    qualified_name: str
    database: str
    schema_name: str
    object_name: str
    column_name: str | None = None
    object_type: str | None = None
    lineage_level: int = 0
    # The nodes one step nearer the starting object (the procedure's
    # PARENT_OBJECT_NAME). Empty for the starting object.
    parent_object_ids: list[str] = Field(default_factory=list)
    parent_qualified_names: list[str] = Field(default_factory=list)
    column_transformation: str | None = None
    transformation_kind: SnowflakeTransformationKind
    # Intermediate CTE/subquery definitions the expression was followed
    # through, outermost first.
    transformation_steps: list[str] = Field(default_factory=list)
    # Column references inside `column_transformation`, as written.
    referenced_columns: list[str] = Field(default_factory=list)
    modification_sql: str | None = None
    modification_sql_source: SnowflakeDefinitionSource | None = None
    modification_query_id: str | None = None
    modification_query_type: str | None = None
    modified_at: datetime | None = None


class SnowflakeDeepLineageResponse(BaseModel):
    account_identifier: str
    starting_object_name: str
    starting_column_name: str | None = None
    object_domain: Literal["TABLE", "COLUMN"]
    direction: Literal["UPSTREAM", "DOWNSTREAM"]
    max_depth: int
    # GET_LINEAGE calls only; definition and history reads are counted in
    # `metadata_query_count`.
    query_count: int = 0
    metadata_query_count: int = 0
    inferred_dependency_count: int = 0
    truncated: bool = False
    snapshot: SnowflakeLineageSnapshot
    transformations: list[SnowflakeColumnTransformation] = Field(default_factory=list)
    warnings: list[SnowflakeLineageWarning] = Field(default_factory=list)
