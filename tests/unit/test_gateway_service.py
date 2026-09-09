from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import UpstreamInvalidResponseError
from app.services.gateway_service import GatewayService


@pytest.mark.asyncio
async def test_list_gateways_maps_gateway_metadata():
    service = GatewayService()
    service.client.get_gateways = AsyncMock(
        return_value=[
            {
                "id": "gateway-1",
                "name": "Warehouse Gateway",
                "type": "Resource",
                "gatewayAnnotation": '{"cluster": true}',
                "gatewayStatus": "Online",
                "publicKey": {
                    "exponent": "AQAB",
                    "modulus": "public-modulus",
                },
            }
        ]
    )

    result = await service.list_gateways(
        access_token="fake-token",
    )

    assert result.count == 1
    assert result.gateways[0].id == "gateway-1"
    assert result.gateways[0].gateway_status == "Online"
    assert result.gateways[0].public_key is not None
    assert result.gateways[0].public_key.exponent == "AQAB"


@pytest.mark.asyncio
async def test_get_datasource_maps_connection_and_credential_metadata():
    service = GatewayService()
    service.client.get_gateway_datasource = AsyncMock(
        return_value={
            "id": "datasource-1",
            "gatewayId": "gateway-1",
            "datasourceType": "Sql",
            "datasourceName": "Warehouse",
            "connectionDetails": ('{"server":"sql.example","database":"warehouse"}'),
            "credentialType": "Windows",
            "credentialDetails": {
                "useEndUserOAuth2Credentials": False,
            },
        }
    )

    result = await service.get_datasource(
        gateway_id="gateway-1",
        datasource_id="datasource-1",
        access_token="fake-token",
    )

    assert result.datasource_type == "Sql"
    assert result.connection_details is not None
    assert result.credential_details is not None
    assert result.credential_details.use_end_user_oauth2_credentials is False


@pytest.mark.asyncio
async def test_list_datasources_maps_gateway_collection():
    service = GatewayService()
    service.client.get_gateway_datasources = AsyncMock(
        return_value=[
            {
                "id": "datasource-1",
                "gatewayId": "gateway-1",
                "datasourceType": "Sql",
                "connectionDetails": '{"server":"sql.example"}',
            }
        ]
    )

    result = await service.list_datasources(
        gateway_id="gateway-1",
        access_token="fake-token",
    )

    assert result.gateway_id == "gateway-1"
    assert result.count == 1
    assert result.datasources[0].id == "datasource-1"


@pytest.mark.asyncio
async def test_get_datasource_rejects_mismatched_provider_ids():
    service = GatewayService()
    service.client.get_gateway_datasource = AsyncMock(
        return_value={
            "id": "unexpected-datasource",
            "gatewayId": "gateway-1",
        }
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_datasource(
            gateway_id="gateway-1",
            datasource_id="datasource-1",
            access_token="fake-token",
        )
