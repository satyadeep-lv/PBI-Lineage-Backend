import asyncio
from time import monotonic
from typing import Any

import httpx

from app.clients.fabric_client import (
    FabricClient,
)
from app.clients.provider_http_client import (
    provider_error_detail_from_payload,
)
from app.core.exceptions import (
    UpstreamInvalidResponseError,
    UpstreamRequestError,
    UpstreamTimeoutError,
)
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
)
from app.schemas.report_definition import (
    ReportDefinition,
    ReportDefinitionPart,
    ReportDefinitionResponse,
)
from app.services.report_definition_normalizer import (
    ReportDefinitionNormalizer,
)


class ReportDefinitionService:
    DEFAULT_RETRY_AFTER_SECONDS = 2

    MAX_TOTAL_WAIT_SECONDS = 120

    def __init__(self) -> None:
        self.client = FabricClient()

    async def _wait_for_definition(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
        initial_response: httpx.Response,
    ) -> ReportDefinitionResponse:
        operation_id = initial_response.headers.get("x-ms-operation-id")

        if not operation_id:
            raise UpstreamInvalidResponseError("fabric")

        deadline = monotonic() + self.MAX_TOTAL_WAIT_SECONDS

        retry_after = self._get_retry_after(initial_response)

        while True:
            remaining = deadline - monotonic()

            if remaining <= 0:
                raise UpstreamTimeoutError("fabric")

            if retry_after > remaining:
                raise UpstreamTimeoutError("fabric")

            await asyncio.sleep(retry_after)

            response = await self.client.get_operation_state(
                operation_id=operation_id,
                access_token=access_token,
            )

            payload = self._parse_object(response)

            status = payload.get("status")

            if status == "Succeeded":
                return await self._get_result(
                    workspace_id=workspace_id,
                    report_id=report_id,
                    operation_id=operation_id,
                    access_token=access_token,
                )

            if status == "Failed":
                raise UpstreamRequestError(
                    "fabric",
                    detail=(provider_error_detail_from_payload(payload)),
                )

            if not isinstance(
                status,
                str,
            ):
                raise UpstreamInvalidResponseError("fabric")

            retry_after = self._get_retry_after(response)

    async def _get_result(
        self,
        *,
        workspace_id: str,
        report_id: str,
        operation_id: str,
        access_token: str,
    ) -> ReportDefinitionResponse:
        response = await self.client.get_operation_result(
            operation_id=operation_id,
            access_token=access_token,
        )

        payload = self._parse_object(response)

        return self._map_definition(
            workspace_id=workspace_id,
            report_id=report_id,
            payload=payload,
        )

    @staticmethod
    def _parse_object(
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

    @staticmethod
    def _map_definition(
        *,
        workspace_id: str,
        report_id: str,
        payload: dict[str, Any],
    ) -> ReportDefinitionResponse:
        raw_definition = payload.get("definition")

        if not isinstance(
            raw_definition,
            dict,
        ):
            raise UpstreamInvalidResponseError("fabric")

        raw_parts = raw_definition.get("parts")

        if not isinstance(
            raw_parts,
            list,
        ):
            raise UpstreamInvalidResponseError("fabric")

        parts: list[ReportDefinitionPart] = []

        for raw_part in raw_parts:
            if not isinstance(
                raw_part,
                dict,
            ):
                raise UpstreamInvalidResponseError("fabric")

            path = raw_part.get("path")

            encoded_payload = raw_part.get("payload")

            payload_type = raw_part.get("payloadType")

            if not isinstance(path, str) or not path:
                raise UpstreamInvalidResponseError("fabric")

            if not isinstance(
                encoded_payload,
                str,
            ):
                raise UpstreamInvalidResponseError("fabric")

            if (
                not isinstance(
                    payload_type,
                    str,
                )
                or not payload_type
            ):
                raise UpstreamInvalidResponseError("fabric")

            parts.append(
                ReportDefinitionPart(
                    path=path,
                    payload=encoded_payload,
                    payload_type=(payload_type),
                )
            )

        definition_format = raw_definition.get("format")

        if definition_format is not None and not isinstance(
            definition_format,
            str,
        ):
            raise UpstreamInvalidResponseError("fabric")

        return ReportDefinitionResponse(
            workspace_id=workspace_id,
            report_id=report_id,
            definition=ReportDefinition(
                format=definition_format,
                parts=parts,
            ),
        )

    def _get_retry_after(
        self,
        response: httpx.Response,
    ) -> int:
        raw_retry_after = response.headers.get("Retry-After")

        if raw_retry_after is None:
            return self.DEFAULT_RETRY_AFTER_SECONDS

        try:
            retry_after = int(raw_retry_after)

        except ValueError:
            return self.DEFAULT_RETRY_AFTER_SECONDS

        if retry_after < 1:
            return self.DEFAULT_RETRY_AFTER_SECONDS

        return retry_after

    async def get_definition(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
        definition_format: str | None = "PBIR",
    ) -> ReportDefinitionResponse:
        response = await self.client.start_report_definition(
            workspace_id=workspace_id,
            report_id=report_id,
            access_token=access_token,
            definition_format=(definition_format),
        )

        if response.status_code == 200:
            payload = self._parse_object(response)

            return self._map_definition(
                workspace_id=workspace_id,
                report_id=report_id,
                payload=payload,
            )

        if response.status_code == 202:
            return await self._wait_for_definition(
                workspace_id=workspace_id,
                report_id=report_id,
                access_token=access_token,
                initial_response=response,
            )

        raise UpstreamInvalidResponseError("fabric")

    async def get_normalized_definition(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
        definition_format: str | None = "PBIR",
    ) -> NormalizedReportDefinitionResponse:
        raw_definition = await self.get_definition(
            workspace_id=workspace_id,
            report_id=report_id,
            access_token=access_token,
            definition_format=(definition_format),
        )

        normalizer = ReportDefinitionNormalizer()

        return normalizer.normalize(raw_definition)
