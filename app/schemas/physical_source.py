from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.gateway import GatewayDatasource
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse

PhysicalSourceKind = Literal[
    "database",
    "file",
    "web",
    "odata",
    "storage",
    "gateway",
    "unknown",
]


class PhysicalDataSource(BaseModel):
    source_id: str
    kind: PhysicalSourceKind
    provider: str
    connector: str | None = None
    server: str | None = None
    database: str | None = None
    schema_name: str | None = None
    object_name: str | None = None
    path: str | None = None
    url: str | None = None
    account: str | None = None
    warehouse: str | None = None
    native_query: str | None = None
    gateway_id: str | None = None
    gateway_datasource_id: str | None = None


class QuerySourceMapping(BaseModel):
    query_id: str
    semantic_table: str
    partition_name: str
    source_path: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class PhysicalSourceWarning(BaseModel):
    code: str
    message: str
    source_path: str | None = None
    datasource_id: str | None = None


class PhysicalSourceDiscoveryRequest(BaseModel):
    semantic_model: ParsedSemanticModelResponse
    gateway_datasources: list[GatewayDatasource] = Field(default_factory=list)


class PhysicalSourceDiscoveryResponse(BaseModel):
    workspace_id: str
    semantic_model_id: str
    sources: list[PhysicalDataSource] = Field(default_factory=list)
    mappings: list[QuerySourceMapping] = Field(default_factory=list)
    warnings: list[PhysicalSourceWarning] = Field(default_factory=list)
    source_count: int = 0
    mapping_count: int = 0
