from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import UpstreamInvalidResponseError
from app.services.semantic_model_service import SemanticModelService


@pytest.mark.asyncio
async def test_list_semantic_models_maps_powerbi_response():
    service = SemanticModelService()

    service.client.get_semantic_models_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "model-1",
                "name": "Enterprise Sales Model",
                "description": "Sales semantic model",
                "isRefreshable": True,
                "isEffectiveIdentityRequired": False,
                "isEffectiveIdentityRolesRequired": False,
                "isOnPremGatewayRequired": False,
                "targetStorageMode": "PremiumFiles",
                "ContentProviderType": "PbixInImportMode",
                "webUrl": "https://app.powerbi.com/model-1",
            }
        ]
    )

    result = await service.list_semantic_models(
        workspace_id="workspace-1",
        access_token="fake-token",
    )

    assert result.workspace_id == "workspace-1"
    assert result.count == 1

    model = result.semantic_models[0]

    assert model.id == "model-1"
    assert model.name == "Enterprise Sales Model"
    assert model.description == "Sales semantic model"
    assert model.is_refreshable is True
    assert model.is_effective_identity_required is False
    assert model.is_effective_identity_roles_required is False
    assert model.is_on_prem_gateway_required is False
    assert model.target_storage_mode == "PremiumFiles"
    assert model.content_provider_type == "PbixInImportMode"
    assert model.web_url == "https://app.powerbi.com/model-1"


@pytest.mark.asyncio
async def test_read_only_semantic_model_with_only_id_and_name():
    service = SemanticModelService()

    service.client.get_semantic_models_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "model-1",
                "name": "Sales Model",
            }
        ]
    )

    result = await service.list_semantic_models(
        workspace_id="workspace-1",
        access_token="fake-token",
    )

    assert result.count == 1

    model = result.semantic_models[0]

    assert model.id == "model-1"
    assert model.name == "Sales Model"

    assert model.description is None
    assert model.is_refreshable is None
    assert model.is_effective_identity_required is None
    assert model.is_effective_identity_roles_required is None
    assert model.is_on_prem_gateway_required is None
    assert model.target_storage_mode is None
    assert model.content_provider_type is None
    assert model.web_url is None


@pytest.mark.asyncio
async def test_list_semantic_models_handles_empty_workspace():
    service = SemanticModelService()

    service.client.get_semantic_models_in_workspace = AsyncMock(return_value=[])

    result = await service.list_semantic_models(
        workspace_id="workspace-1",
        access_token="fake-token",
    )

    assert result.workspace_id == "workspace-1"
    assert result.count == 0
    assert result.semantic_models == []


@pytest.mark.asyncio
async def test_semantic_model_missing_id_raises_invalid_response():
    service = SemanticModelService()

    service.client.get_semantic_models_in_workspace = AsyncMock(
        return_value=[
            {
                "name": "Sales Model",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_semantic_models(
            workspace_id="workspace-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_semantic_model_missing_name_raises_invalid_response():
    service = SemanticModelService()

    service.client.get_semantic_models_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "model-1",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_semantic_models(
            workspace_id="workspace-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_semantic_model_empty_id_raises_invalid_response():
    service = SemanticModelService()

    service.client.get_semantic_models_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "",
                "name": "Sales Model",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_semantic_models(
            workspace_id="workspace-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_semantic_model_empty_name_raises_invalid_response():
    service = SemanticModelService()

    service.client.get_semantic_models_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "model-1",
                "name": "",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_semantic_models(
            workspace_id="workspace-1",
            access_token="fake-token",
        )
