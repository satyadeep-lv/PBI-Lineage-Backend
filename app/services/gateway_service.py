from typing import Any

from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import UpstreamInvalidResponseError
from app.schemas.gateway import (
    Gateway,
    GatewayDatasource,
    GatewayDatasourceCredentialDetails,
    GatewayDatasourceListResponse,
    GatewayListResponse,
    GatewayPublicKey,
)


class GatewayService:
    def __init__(self) -> None:
        self.client = PowerBIClient()

    async def list_gateways(
        self,
        *,
        access_token: str,
    ) -> GatewayListResponse:
        raw_gateways = await self.client.get_gateways(
            access_token=access_token,
        )

        gateways = [self._map_gateway(gateway) for gateway in raw_gateways]

        return GatewayListResponse(
            gateways=gateways,
            count=len(gateways),
        )

    async def get_datasource(
        self,
        *,
        gateway_id: str,
        datasource_id: str,
        access_token: str,
    ) -> GatewayDatasource:
        raw_datasource = await self.client.get_gateway_datasource(
            gateway_id=gateway_id,
            datasource_id=datasource_id,
            access_token=access_token,
        )

        return self._map_datasource(
            raw_datasource,
            gateway_id=gateway_id,
            datasource_id=datasource_id,
        )

    async def list_datasources(
        self,
        *,
        gateway_id: str,
        access_token: str,
    ) -> GatewayDatasourceListResponse:
        raw_datasources = await self.client.get_gateway_datasources(
            gateway_id=gateway_id,
            access_token=access_token,
        )
        datasources = [
            self._map_datasource(
                datasource,
                gateway_id=gateway_id,
                datasource_id=self._required_text(datasource, "id"),
            )
            for datasource in raw_datasources
        ]

        return GatewayDatasourceListResponse(
            gateway_id=gateway_id,
            datasources=datasources,
            count=len(datasources),
        )

    @staticmethod
    def _map_gateway(
        gateway: dict[str, Any],
    ) -> Gateway:
        gateway_id = GatewayService._required_text(
            gateway,
            "id",
        )
        name = GatewayService._required_text(
            gateway,
            "name",
        )
        gateway_type = GatewayService._required_text(
            gateway,
            "type",
        )
        public_key = gateway.get("publicKey")

        if public_key is not None and not isinstance(
            public_key,
            dict,
        ):
            raise UpstreamInvalidResponseError("powerbi")

        return Gateway(
            id=gateway_id,
            name=name,
            type=gateway_type,
            gateway_annotation=GatewayService._optional_text(
                gateway,
                "gatewayAnnotation",
            ),
            gateway_status=GatewayService._optional_text(
                gateway,
                "gatewayStatus",
            ),
            public_key=(
                GatewayPublicKey(
                    exponent=GatewayService._optional_text(
                        public_key,
                        "exponent",
                    ),
                    modulus=GatewayService._optional_text(
                        public_key,
                        "modulus",
                    ),
                )
                if public_key is not None
                else None
            ),
        )

    @staticmethod
    def _map_datasource(
        datasource: dict[str, Any],
        *,
        gateway_id: str,
        datasource_id: str,
    ) -> GatewayDatasource:
        returned_datasource_id = GatewayService._required_text(
            datasource,
            "id",
        )
        returned_gateway_id = GatewayService._required_text(
            datasource,
            "gatewayId",
        )

        if returned_datasource_id != datasource_id or returned_gateway_id != gateway_id:
            raise UpstreamInvalidResponseError("powerbi")

        credential_details = datasource.get("credentialDetails")

        if credential_details is not None and not isinstance(
            credential_details,
            dict,
        ):
            raise UpstreamInvalidResponseError("powerbi")

        use_end_user_oauth2_credentials = (
            credential_details.get("useEndUserOAuth2Credentials")
            if credential_details is not None
            else None
        )

        if use_end_user_oauth2_credentials is not None and not isinstance(
            use_end_user_oauth2_credentials,
            bool,
        ):
            raise UpstreamInvalidResponseError("powerbi")

        return GatewayDatasource(
            id=returned_datasource_id,
            gateway_id=returned_gateway_id,
            datasource_type=GatewayService._optional_text(
                datasource,
                "datasourceType",
            ),
            datasource_name=GatewayService._optional_text(
                datasource,
                "datasourceName",
            ),
            connection_details=GatewayService._optional_text(
                datasource,
                "connectionDetails",
            ),
            credential_type=GatewayService._optional_text(
                datasource,
                "credentialType",
            ),
            credential_details=(
                GatewayDatasourceCredentialDetails(
                    use_end_user_oauth2_credentials=(use_end_user_oauth2_credentials),
                )
                if credential_details is not None
                else None
            ),
        )

    @staticmethod
    def _required_text(
        payload: dict[str, Any],
        key: str,
    ) -> str:
        value = GatewayService._optional_text(
            payload,
            key,
        )

        if value is None:
            raise UpstreamInvalidResponseError("powerbi")

        return value

    @staticmethod
    def _optional_text(
        payload: dict[str, Any],
        key: str,
    ) -> str | None:
        value = payload.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

        if value is None:
            return None

        raise UpstreamInvalidResponseError("powerbi")
