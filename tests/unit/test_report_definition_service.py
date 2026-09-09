from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.exceptions import (
    UpstreamInvalidResponseError,
    UpstreamRequestError,
)
from app.services.report_definition_service import (
    ReportDefinitionService,
)


@pytest.mark.asyncio
async def test_immediate_report_definition():
    service = ReportDefinitionService()

    response = httpx.Response(
        status_code=200,
        json={
            "definition": {
                "parts": [
                    {
                        "path": ("definition.pbir"),
                        "payload": "YWJj",
                        "payloadType": ("InlineBase64"),
                    }
                ]
            }
        },
    )

    service.client.start_report_definition = AsyncMock(return_value=response)

    result = await service.get_definition(
        workspace_id="workspace-1",
        report_id="report-1",
        access_token="fake-token",
    )

    assert result.workspace_id == ("workspace-1")

    assert result.report_id == ("report-1")

    assert len(result.definition.parts) == 1

    part = result.definition.parts[0]

    assert part.path == "definition.pbir"

    assert part.payload == "YWJj"

    assert part.payload_type == "InlineBase64"

    (
        service.client.start_report_definition.assert_awaited_once_with(
            workspace_id="workspace-1",
            report_id="report-1",
            access_token="fake-token",
            definition_format="PBIR",
        )
    )


@pytest.mark.asyncio
async def test_definition_missing_definition():
    service = ReportDefinitionService()

    response = httpx.Response(
        status_code=200,
        json={},
    )

    service.client.start_report_definition = AsyncMock(return_value=response)

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_definition(
            workspace_id="workspace-1",
            report_id="report-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_definition_missing_parts():
    service = ReportDefinitionService()

    response = httpx.Response(
        status_code=200,
        json={"definition": {}},
    )

    service.client.start_report_definition = AsyncMock(return_value=response)

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_definition(
            workspace_id="workspace-1",
            report_id="report-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_202_requires_operation_id():
    service = ReportDefinitionService()

    response = httpx.Response(
        status_code=202,
        headers={
            "Retry-After": "1",
        },
    )

    service.client.start_report_definition = AsyncMock(return_value=response)

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_definition(
            workspace_id="workspace-1",
            report_id="report-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_lro_report_definition_success(
    monkeypatch,
):
    service = ReportDefinitionService()

    initial_response = httpx.Response(
        status_code=202,
        headers={
            "x-ms-operation-id": ("operation-1"),
            "Retry-After": "1",
        },
    )

    state_response = httpx.Response(
        status_code=200,
        headers={
            "Retry-After": "1",
        },
        json={"status": "Succeeded"},
    )

    result_response = httpx.Response(
        status_code=200,
        json={
            "definition": {
                "parts": [
                    {
                        "path": ("definition.pbir"),
                        "payload": ("YWJj"),
                        "payloadType": ("InlineBase64"),
                    }
                ]
            }
        },
    )

    service.client.start_report_definition = AsyncMock(return_value=(initial_response))

    service.client.get_operation_state = AsyncMock(return_value=(state_response))

    service.client.get_operation_result = AsyncMock(return_value=(result_response))

    async def no_wait(
        _: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        "app.services.report_definition_service.asyncio.sleep",
        no_wait,
    )

    result = await service.get_definition(
        workspace_id="workspace-1",
        report_id="report-1",
        access_token="fake-token",
    )

    assert len(result.definition.parts) == 1

    service.client.get_operation_state.assert_awaited_once()

    service.client.get_operation_result.assert_awaited_once()


@pytest.mark.asyncio
async def test_lro_report_definition_failed_status_includes_detail(
    monkeypatch,
):
    service = ReportDefinitionService()

    service.client.start_report_definition = AsyncMock(
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
                    "errorCode": ("InvalidFormat"),
                    "message": ("Report format is invalid."),
                },
            },
        )
    )

    async def no_wait(
        _: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        "app.services.report_definition_service.asyncio.sleep",
        no_wait,
    )

    with pytest.raises(UpstreamRequestError) as exc_info:
        await service.get_definition(
            workspace_id="workspace-1",
            report_id="report-1",
            access_token="fake-token",
        )

    assert "InvalidFormat" in (exc_info.value.message)
    assert "Report format is invalid." in (exc_info.value.message)
