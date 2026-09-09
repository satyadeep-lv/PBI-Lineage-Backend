from typing import Any

from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import UpstreamInvalidResponseError
from app.schemas.semantic_model import (
    SemanticModel,
    SemanticModelListResponse,
)


class SemanticModelService:
    def __init__(self) -> None:
        self.client = PowerBIClient()

    async def list_semantic_models(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> SemanticModelListResponse:
        raw_models = await self.client.get_semantic_models_in_workspace(
            workspace_id=workspace_id,
            access_token=access_token,
        )

        semantic_models = [self._map_semantic_model(model) for model in raw_models]

        return SemanticModelListResponse(
            workspace_id=workspace_id,
            semantic_models=semantic_models,
            count=len(semantic_models),
        )

    @staticmethod
    def _map_semantic_model(
        model: dict[str, Any],
    ) -> SemanticModel:
        model_id = model.get("id")
        model_name = model.get("name")

        if not isinstance(model_id, str) or not model_id:
            raise UpstreamInvalidResponseError("powerbi")

        if not isinstance(model_name, str) or not model_name:
            raise UpstreamInvalidResponseError("powerbi")

        return SemanticModel(
            id=model_id,
            name=model_name,
            description=model.get("description"),
            is_refreshable=model.get("isRefreshable"),
            is_effective_identity_required=(model.get("isEffectiveIdentityRequired")),
            is_effective_identity_roles_required=(
                model.get("isEffectiveIdentityRolesRequired")
            ),
            is_on_prem_gateway_required=(model.get("isOnPremGatewayRequired")),
            target_storage_mode=model.get("targetStorageMode"),
            content_provider_type=model.get("ContentProviderType"),
            web_url=model.get("webUrl"),
        )
