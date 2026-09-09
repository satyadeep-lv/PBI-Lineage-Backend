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


class SnowflakeDeepLineageResponse(BaseModel):
    account_identifier: str
    starting_object_name: str
    starting_column_name: str | None = None
    object_domain: Literal["TABLE", "COLUMN"]
    direction: Literal["UPSTREAM", "DOWNSTREAM"]
    max_depth: int
    query_count: int = 0
    truncated: bool = False
    snapshot: SnowflakeLineageSnapshot
    warnings: list[SnowflakeLineageWarning] = Field(default_factory=list)
