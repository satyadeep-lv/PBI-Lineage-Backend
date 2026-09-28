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

    # -- Org apps ---------------------------------------------------------

    async def get_workspace(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="fabric",
            url=f"{self.BASE_URL}/workspaces/{workspace_id}",
            access_token=access_token,
            not_found_resource="workspace",
            cacheable=True,
        )

        return self._parse_object_response(response)

    async def get_org_app(
        self,
        *,
        workspace_id: str,
        org_app_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="fabric",
            url=f"{self.BASE_URL}/workspaces/{workspace_id}/orgApps/{org_app_id}",
            access_token=access_token,
            not_found_resource="org app",
            cacheable=True,
        )

        return self._parse_object_response(response)

    async def list_org_app_audiences(
        self,
        *,
        workspace_id: str,
        access_token: str,
        continuation_token: str | None = None,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="fabric",
            url=f"{self.BASE_URL}/workspaces/{workspace_id}/orgAppAudiences",
            access_token=access_token,
            params=(
                {"continuationToken": continuation_token}
                if continuation_token
                else None
            ),
            not_found_resource="workspace",
            cacheable=True,
        )

        return self._parse_object_response(response)

    async def start_org_app_definition(
        self,
        *,
        workspace_id: str,
        org_app_id: str,
        access_token: str,
    ) -> httpx.Response:
        return await provider_post(
            provider="fabric",
            url=(
                f"{self.BASE_URL}/workspaces/{workspace_id}/orgApps/"
                f"{org_app_id}/getDefinition"
            ),
            access_token=access_token,
            not_found_resource="org app",
        )

    async def start_org_app_audience_definition(
        self,
        *,
        workspace_id: str,
        audience_id: str,
        access_token: str,
    ) -> httpx.Response:
        return await provider_post(
            provider="fabric",
            url=(
                f"{self.BASE_URL}/workspaces/{workspace_id}/orgAppAudiences/"
                f"{audience_id}/getDefinition"
            ),
            access_token=access_token,
            not_found_resource="org app audience",
        )

    async def list_workspace_role_assignments(
        self,
        *,
        workspace_id: str,
        access_token: str,
        continuation_token: str | None = None,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="fabric",
            url=f"{self.BASE_URL}/workspaces/{workspace_id}/roleAssignments",
            access_token=access_token,
            params=(
                {"continuationToken": continuation_token}
                if continuation_token
                else None
            ),
            not_found_resource="workspace",
            cacheable=True,
        )

        return self._parse_object_response(response)

    async def list_item_access_details_as_admin(
        self,
        *,
        workspace_id: str,
        item_id: str,
        access_token: str,
        item_type: str | None = None,
    ) -> dict[str, Any]:
        """Principals with access to one item (Fabric admin, preview).

        ``type`` is required by the API for Report, Dashboard, SemanticModel,
        App and Dataflow items and optional for the rest.
        """
        response = await provider_get(
            provider="fabric",
            url=(
                f"{self.BASE_URL}/admin/workspaces/{workspace_id}/items/{item_id}/users"
            ),
            access_token=access_token,
            params={"type": item_type} if item_type else None,
            not_found_resource="item",
            cacheable=True,
        )

        return self._parse_object_response(response)

    async def list_items(
        self,
        *,
        workspace_id: str,
        access_token: str,
        continuation_token: str | None = None,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="fabric",
            url=f"{self.BASE_URL}/workspaces/{workspace_id}/items",
            access_token=access_token,
            params=(
                {"continuationToken": continuation_token}
                if continuation_token
                else None
            ),
            not_found_resource="workspace",
            cacheable=True,
        )

        return self._parse_object_response(response)
