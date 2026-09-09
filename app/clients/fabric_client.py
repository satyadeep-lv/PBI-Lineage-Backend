from typing import Any

import httpx

from app.clients.provider_http_client import (
    provider_get,
    provider_post,
)
from app.core.exceptions import (
    UpstreamInvalidResponseError,
)


class FabricClient:
    BASE_URL = "https://api.fabric.microsoft.com/v1"

    @staticmethod
    def _parse_object_response(
        response: httpx.Response,
    ) -> dict[str, Any]:
        try:
            payload = response.json()

        except ValueError as exc:
            raise UpstreamInvalidResponseError("fabric") from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise UpstreamInvalidResponseError("fabric")

        return payload

    async def validate_connection(
        self,
        access_token: str,
    ) -> bool:
        await provider_get(
            provider="fabric",
            url=(f"{self.BASE_URL}/workspaces"),
            access_token=access_token,
        )

        return True

    async def start_report_definition(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
        definition_format: str | None = "PBIR",
    ) -> httpx.Response:
        params = None

        if definition_format:
            params = {
                "format": (definition_format),
            }

        return await provider_post(
            provider="fabric",
            url=(
                f"{self.BASE_URL}/workspaces/"
                f"{workspace_id}/reports/"
                f"{report_id}/getDefinition"
            ),
            access_token=access_token,
            params=params,
            not_found_resource="report",
        )

    async def start_semantic_model_definition(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        definition_format: str = "TMDL",
    ) -> httpx.Response:
        return await provider_post(
            provider="fabric",
            url=(
                f"{self.BASE_URL}/workspaces/"
                f"{workspace_id}/semanticModels/"
                f"{semantic_model_id}/"
                "getDefinition"
            ),
            access_token=access_token,
            params={
                "format": definition_format,
            },
            not_found_resource=("semantic_model"),
        )

    async def get_operation_state(
        self,
        *,
        operation_id: str,
        access_token: str,
    ) -> httpx.Response:
        return await provider_get(
            provider="fabric",
            url=(f"{self.BASE_URL}/operations/{operation_id}"),
            access_token=access_token,
        )

    async def get_operation_result(
        self,
        *,
        operation_id: str,
        access_token: str,
    ) -> httpx.Response:
        return await provider_get(
            provider="fabric",
            url=(f"{self.BASE_URL}/operations/{operation_id}/result"),
            access_token=access_token,
        )
