from pydantic import BaseModel


class SemanticModel(BaseModel):
    id: str
    name: str

    description: str | None = None

    is_refreshable: bool | None = None

    is_effective_identity_required: bool | None = None

    is_effective_identity_roles_required: bool | None = None

    is_on_prem_gateway_required: bool | None = None

    target_storage_mode: str | None = None

    content_provider_type: str | None = None

    web_url: str | None = None


class SemanticModelListResponse(BaseModel):
    workspace_id: str

    semantic_models: list[SemanticModel]

    count: int
