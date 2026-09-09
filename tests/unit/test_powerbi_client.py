from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients.powerbi_client import PowerBIClient


@pytest.mark.asyncio
async def test_get_report_in_my_workspace_uses_my_workspace_url(
    monkeypatch,
):
    provider_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "id": "report-1",
                "name": "Sales Report",
            },
        )
    )
    monkeypatch.setattr(
        "app.clients.powerbi_client.provider_get",
        provider_get,
    )

    result = await PowerBIClient().get_report_in_my_workspace(
        report_id="report-1",
        access_token="fake-token",
    )

    assert result["id"] == "report-1"
    provider_get.assert_awaited_once_with(
        provider="powerbi",
        url=("https://api.powerbi.com/v1.0/myorg/reports/report-1"),
        access_token="fake-token",
        not_found_resource="report",
    )


@pytest.mark.asyncio
async def test_get_gateways_uses_gateway_collection_url(
    monkeypatch,
):
    provider_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "gateway-1",
                        "name": "Warehouse Gateway",
                        "type": "Resource",
                    }
                ]
            },
        )
    )
    monkeypatch.setattr(
        "app.clients.powerbi_client.provider_get",
        provider_get,
    )

    result = await PowerBIClient().get_gateways(
        access_token="fake-token",
    )

    assert result[0]["id"] == "gateway-1"
    provider_get.assert_awaited_once_with(
        provider="powerbi",
        url=("https://api.powerbi.com/v1.0/myorg/gateways"),
        access_token="fake-token",
    )


@pytest.mark.asyncio
async def test_get_gateway_datasource_uses_gateway_datasource_url(
    monkeypatch,
):
    provider_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "id": "datasource-1",
                "gatewayId": "gateway-1",
            },
        )
    )
    monkeypatch.setattr(
        "app.clients.powerbi_client.provider_get",
        provider_get,
    )

    result = await PowerBIClient().get_gateway_datasource(
        gateway_id="gateway-1",
        datasource_id="datasource-1",
        access_token="fake-token",
    )

    assert result["gatewayId"] == "gateway-1"
    provider_get.assert_awaited_once_with(
        provider="powerbi",
        url=(
            "https://api.powerbi.com/v1.0/myorg/"
            "gateways/gateway-1/datasources/datasource-1"
        ),
        access_token="fake-token",
        not_found_resource="gateway datasource",
    )


@pytest.mark.asyncio
async def test_get_gateway_datasources_uses_gateway_collection_url(
    monkeypatch,
):
    provider_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "datasource-1",
                        "gatewayId": "gateway-1",
                    }
                ]
            },
        )
    )
    monkeypatch.setattr(
        "app.clients.powerbi_client.provider_get",
        provider_get,
    )

    result = await PowerBIClient().get_gateway_datasources(
        gateway_id="gateway-1",
        access_token="fake-token",
    )

    assert result[0]["id"] == "datasource-1"
    provider_get.assert_awaited_once_with(
        provider="powerbi",
        url=("https://api.powerbi.com/v1.0/myorg/gateways/gateway-1/datasources"),
        access_token="fake-token",
    )
