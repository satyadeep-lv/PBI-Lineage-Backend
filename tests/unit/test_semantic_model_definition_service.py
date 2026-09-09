from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.exceptions import (
    UpstreamInvalidResponseError,
    UpstreamRequestError,
)
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)


def _definition_payload(
    *,
    definition_format: str = "TMDL",
) -> dict:
    return {
        "definition": {
            "format": definition_format,
            "parts": [
                {
                    "path": ("definition/model.tmdl"),
                    "payload": ("bW9kZWwgTW9kZWw="),
                    "payloadType": ("InlineBase64"),
                },
                {
                    "path": ("definition/tables/Sales.tmdl"),
                    "payload": ("dGFibGUgU2FsZXM="),
                    "payloadType": ("InlineBase64"),
                },
            ],
        }
    }


@pytest.mark.asyncio
async def test_get_semantic_model_definition_maps_immediate_response():
    service = SemanticModelDefinitionService()

    response = httpx.Response(
        status_code=200,
        json=_definition_payload(),
    )

    service.client.start_semantic_model_definition = AsyncMock(return_value=response)

    result = await service.get_definition(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        access_token="token",
        definition_format="TMDL",
    )

    assert result.workspace_id == "workspace-123"
    assert result.semantic_model_id == "model-123"
    assert result.definition.format == "TMDL"
    assert len(result.definition.parts) == 2

    first_part = result.definition.parts[0]

    assert first_part.path == "definition/model.tmdl"
    assert first_part.payload == "bW9kZWwgTW9kZWw="
    assert first_part.payload_type == "InlineBase64"

    serialized = result.model_dump(by_alias=True)

    assert serialized["definition"]["parts"][0]["payloadType"] == "InlineBase64"
    assert "payload_type" not in serialized["definition"]["parts"][0]

    (
        service.client.start_semantic_model_definition.assert_awaited_once_with(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
            definition_format="TMDL",
        )
    )


@pytest.mark.asyncio
async def test_get_semantic_model_definition_rejects_missing_definition():
    service = SemanticModelDefinitionService()

    service.client.start_semantic_model_definition = AsyncMock(
        return_value=httpx.Response(
            status_code=200,
            json={},
        )
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_definition(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
        )


@pytest.mark.asyncio
async def test_get_semantic_model_definition_rejects_missing_parts():
    service = SemanticModelDefinitionService()

    service.client.start_semantic_model_definition = AsyncMock(
        return_value=httpx.Response(
            status_code=200,
            json={"definition": {}},
        )
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_definition(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
        )


@pytest.mark.asyncio
async def test_get_semantic_model_definition_rejects_invalid_part():
    service = SemanticModelDefinitionService()

    service.client.start_semantic_model_definition = AsyncMock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "definition": {
                    "parts": [
                        {
                            "path": "",
                            "payload": "abc",
                            "payloadType": ("InlineBase64"),
                        }
                    ]
                }
            },
        )
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_definition(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
        )


@pytest.mark.asyncio
async def test_accepted_semantic_model_definition_requires_operation_id():
    service = SemanticModelDefinitionService()

    service.client.start_semantic_model_definition = AsyncMock(
        return_value=httpx.Response(
            status_code=202,
            headers={
                "Retry-After": "1",
            },
        )
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_definition(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
        )


@pytest.mark.asyncio
async def test_lro_semantic_model_definition_success(
    monkeypatch,
):
    service = SemanticModelDefinitionService()

    service.client.start_semantic_model_definition = AsyncMock(
        return_value=httpx.Response(
            status_code=202,
            headers={
                "x-ms-operation-id": ("operation-123"),
                "Retry-After": "1",
            },
        )
    )
    service.client.get_operation_state = AsyncMock(
        return_value=httpx.Response(
            status_code=200,
            headers={
                "Retry-After": "1",
            },
            json={"status": "Succeeded"},
        )
    )
    service.client.get_operation_result = AsyncMock(
        return_value=httpx.Response(
            status_code=200,
            json=_definition_payload(),
        )
    )

    async def no_wait(
        _: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        "app.services.semantic_model_definition_service.asyncio.sleep",
        no_wait,
    )

    result = await service.get_definition(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        access_token="token",
        definition_format="TMSL",
    )

    assert result.semantic_model_id == "model-123"
    assert len(result.definition.parts) == 2

    (
        service.client.get_operation_state.assert_awaited_once_with(
            operation_id="operation-123",
            access_token="token",
        )
    )
    (
        service.client.get_operation_result.assert_awaited_once_with(
            operation_id="operation-123",
            access_token="token",
        )
    )


@pytest.mark.asyncio
async def test_lro_semantic_model_definition_failed_status(
    monkeypatch,
):
    service = SemanticModelDefinitionService()

    service.client.start_semantic_model_definition = AsyncMock(
        return_value=httpx.Response(
            status_code=202,
            headers={
                "x-ms-operation-id": ("operation-123"),
                "Retry-After": "1",
            },
        )
    )
    service.client.get_operation_state = AsyncMock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "status": "Failed",
                "error": {
                    "errorCode": ("OperationFailed"),
                    "message": ("Semantic model export failed."),
                },
            },
        )
    )

    async def no_wait(
        _: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        "app.services.semantic_model_definition_service.asyncio.sleep",
        no_wait,
    )

    with pytest.raises(UpstreamRequestError) as exc_info:
        await service.get_definition(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
        )

    assert "OperationFailed" in (exc_info.value.message)
    assert "Semantic model export failed." in exc_info.value.message
