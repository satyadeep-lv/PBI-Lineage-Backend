from typing import Any

import httpx

from app.clients.provider_http_client import (
    provider_get,
    provider_post,
)
from app.core.exceptions import UpstreamInvalidResponseError


class PowerBIClient:
    BASE_URL = "https://api.powerbi.com/v1.0/myorg"

    @staticmethod
    def _parse_object_response(
        response: httpx.Response,
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamInvalidResponseError("powerbi") from exc

        if not isinstance(payload, dict):
            raise UpstreamInvalidResponseError("powerbi")

        return payload

    @staticmethod
    def _parse_list_response(
        response: httpx.Response,
    ) -> list[dict[str, Any]]:
        payload = PowerBIClient._parse_object_response(response)

        items = payload.get("value")

        if not isinstance(items, list):
            raise UpstreamInvalidResponseError("powerbi")

        if not all(isinstance(item, dict) for item in items):
            raise UpstreamInvalidResponseError("powerbi")

        return items

    @staticmethod
    def _parse_array_response(
        response: httpx.Response,
    ) -> list[dict[str, Any]]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamInvalidResponseError("powerbi") from exc

        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise UpstreamInvalidResponseError("powerbi")
        return payload

    async def validate_connection(
        self,
        access_token: str,
    ) -> bool:
        await provider_get(
            provider="powerbi",
            url=f"{self.BASE_URL}/groups",
            access_token=access_token,
            params={
                "$top": 1,
            },
        )

        return True

    async def get_workspaces(
        self,
        *,
        access_token: str,
        top: int,
        skip: int,
    ) -> list[dict[str, Any]]:
        response = await provider_get(
            provider="powerbi",
            url=f"{self.BASE_URL}/groups",
            access_token=access_token,
            params={
                "$top": top,
                "$skip": skip,
            },
        )

        return self._parse_list_response(response)

    async def get_workspace(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/groups/{workspace_id}"),
            access_token=access_token,
        )

        return self._parse_object_response(response)

    async def get_reports_in_workspace(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> list[dict[str, Any]]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/groups/{workspace_id}/reports"),
            access_token=access_token,
        )

        return self._parse_list_response(response)

    async def get_semantic_models_in_workspace(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> list[dict[str, Any]]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/groups/{workspace_id}/datasets"),
            access_token=access_token,
        )

        return self._parse_list_response(response)

    async def get_report(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/groups/{workspace_id}/reports/{report_id}"),
            access_token=access_token,
        )

        return self._parse_object_response(response)

    async def get_report_in_my_workspace(
        self,
        *,
        report_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/reports/{report_id}"),
            access_token=access_token,
            not_found_resource="report",
        )

        return self._parse_object_response(response)

    async def get_gateways(
        self,
        *,
        access_token: str,
    ) -> list[dict[str, Any]]:
        response = await provider_get(
            provider="powerbi",
            url=f"{self.BASE_URL}/gateways",
            access_token=access_token,
        )

        return self._parse_list_response(response)

    async def get_gateway_datasource(
        self,
        *,
        gateway_id: str,
        datasource_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/gateways/{gateway_id}/datasources/{datasource_id}"),
            access_token=access_token,
            not_found_resource="gateway datasource",
        )

        return self._parse_object_response(response)

    async def get_gateway_datasources(
        self,
        *,
        gateway_id: str,
        access_token: str,
    ) -> list[dict[str, Any]]:
        response = await provider_get(
            provider="powerbi",
            url=f"{self.BASE_URL}/gateways/{gateway_id}/datasources",
            access_token=access_token,
        )

        return self._parse_list_response(response)

    async def get_modified_workspaces(
        self,
        *,
        access_token: str,
        modified_since: str | None,
        exclude_personal_workspaces: bool,
        exclude_inactive_workspaces: bool,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "excludePersonalWorkspaces": exclude_personal_workspaces,
            "excludeInActiveWorkspaces": exclude_inactive_workspaces,
        }
        if modified_since is not None:
            params["modifiedSince"] = modified_since

        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/admin/workspaces/modified"),
            access_token=access_token,
            params=params,
        )
        return self._parse_array_response(response)

    async def start_workspace_scan(
        self,
        *,
        access_token: str,
        workspace_ids: list[str],
        lineage: bool,
        datasource_details: bool,
        dataset_schema: bool,
        dataset_expressions: bool,
        get_artifact_users: bool,
    ) -> dict[str, Any]:
        response = await provider_post(
            provider="powerbi",
            url=(f"{self.BASE_URL}/admin/workspaces/getInfo"),
            access_token=access_token,
            params={
                "lineage": lineage,
                "datasourceDetails": datasource_details,
                "datasetSchema": dataset_schema,
                "datasetExpressions": dataset_expressions,
                "getArtifactUsers": get_artifact_users,
            },
            json_body={"workspaces": workspace_ids},
        )
        return self._parse_object_response(response)

    async def get_workspace_scan_status(
        self,
        *,
        access_token: str,
        scan_id: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/admin/workspaces/scanStatus/{scan_id}"),
            access_token=access_token,
            not_found_resource="scanner scan",
        )
        return self._parse_object_response(response)

    async def get_workspace_scan_result(
        self,
        *,
        access_token: str,
        scan_id: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/admin/workspaces/scanResult/{scan_id}"),
            access_token=access_token,
            not_found_resource="scanner scan",
        )
        return self._parse_object_response(response)

    async def get_report_pages(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
    ) -> list[dict[str, Any]]:
        response = await provider_get(
            provider="powerbi",
            url=(f"{self.BASE_URL}/groups/{workspace_id}/reports/{report_id}/pages"),
            access_token=access_token,
        )

        return self._parse_list_response(response)

    async def get_report_page(
        self,
        *,
        workspace_id: str,
        report_id: str,
        page_name: str,
        access_token: str,
    ) -> dict[str, Any]:
        response = await provider_get(
            provider="powerbi",
            url=(
                f"{self.BASE_URL}/groups/"
                f"{workspace_id}/reports/"
                f"{report_id}/pages/"
                f"{page_name}"
            ),
            access_token=access_token,
        )

        return self._parse_object_response(response)
