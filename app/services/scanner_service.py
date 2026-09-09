from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import UpstreamInvalidResponseError
from app.schemas.scanner import (
    ScannerErrorDetail,
    ScannerModifiedWorkspacesResponse,
    ScannerResultResponse,
    ScannerResultSummary,
    ScannerScanResponse,
    ScannerWorkspaceScanRequest,
)


class ScannerService:
    def __init__(
        self,
        client: PowerBIClient | None = None,
    ) -> None:
        self.client = client or PowerBIClient()

    async def list_modified_workspaces(
        self,
        *,
        access_token: str,
        modified_since: datetime | None,
        exclude_personal_workspaces: bool,
        exclude_inactive_workspaces: bool,
    ) -> ScannerModifiedWorkspacesResponse:
        normalized_since = None
        if modified_since is not None:
            if modified_since.tzinfo is None:
                modified_since = modified_since.replace(tzinfo=UTC)
            normalized_since = (
                modified_since.astimezone(UTC).isoformat().replace("+00:00", "Z")
            )

        raw_workspaces = await self.client.get_modified_workspaces(
            access_token=access_token,
            modified_since=normalized_since,
            exclude_personal_workspaces=exclude_personal_workspaces,
            exclude_inactive_workspaces=exclude_inactive_workspaces,
        )
        try:
            workspace_ids = [
                UUID(self._required_text(workspace, "id"))
                for workspace in raw_workspaces
            ]
        except ValueError as exc:
            raise UpstreamInvalidResponseError("powerbi") from exc

        return ScannerModifiedWorkspacesResponse(
            workspaces=workspace_ids,
            count=len(workspace_ids),
        )

    async def start_scan(
        self,
        *,
        access_token: str,
        request: ScannerWorkspaceScanRequest,
    ) -> ScannerScanResponse:
        payload = await self.client.start_workspace_scan(
            access_token=access_token,
            workspace_ids=[str(item) for item in request.workspaces],
            lineage=request.lineage,
            datasource_details=request.datasource_details,
            dataset_schema=request.dataset_schema,
            dataset_expressions=request.dataset_expressions,
            get_artifact_users=request.get_artifact_users,
        )
        return self._map_scan(payload)

    async def get_scan_status(
        self,
        *,
        access_token: str,
        scan_id: str,
    ) -> ScannerScanResponse:
        payload = await self.client.get_workspace_scan_status(
            access_token=access_token,
            scan_id=scan_id,
        )
        result = self._map_scan(payload)
        if str(result.scan_id) != scan_id:
            raise UpstreamInvalidResponseError("powerbi")
        return result

    async def get_scan_result(
        self,
        *,
        access_token: str,
        scan_id: str,
    ) -> ScannerResultResponse:
        payload = await self.client.get_workspace_scan_result(
            access_token=access_token,
            scan_id=scan_id,
        )
        summary = self._summarize_result(payload)
        return ScannerResultResponse(
            scan_id=UUID(scan_id),
            sections=sorted(payload),
            summary=summary,
            payload=payload,
        )

    @classmethod
    def _map_scan(
        cls,
        payload: dict[str, Any],
    ) -> ScannerScanResponse:
        raw_error = payload.get("error")
        if raw_error is not None and not isinstance(raw_error, dict):
            raise UpstreamInvalidResponseError("powerbi")

        error = None
        if isinstance(raw_error, dict):
            error = ScannerErrorDetail(
                code=cls._optional_text(raw_error, "code"),
                message=cls._optional_text(raw_error, "message"),
                target=cls._optional_text(raw_error, "target"),
            )

        try:
            return ScannerScanResponse(
                scan_id=cls._required_text(payload, "id"),
                created_at=cls._required_text(
                    payload,
                    "createdDateTime",
                ),
                status=cls._required_text(payload, "status"),
                error=error,
            )
        except ValidationError as exc:
            raise UpstreamInvalidResponseError("powerbi") from exc

    @classmethod
    def _summarize_result(
        cls,
        payload: dict[str, Any],
    ) -> ScannerResultSummary:
        workspaces = cls._list(payload, "workspaces", required=True)
        datasource_instances = cls._list(
            payload,
            "datasourceInstances",
        )
        misconfigured_instances = cls._list(
            payload,
            "misconfiguredDatasourceInstances",
        )
        summary = ScannerResultSummary(
            workspace_count=len(workspaces),
            datasource_instance_count=len(datasource_instances),
            misconfigured_datasource_instance_count=(len(misconfigured_instances)),
        )

        for workspace in workspaces:
            reports = cls._list(workspace, "reports")
            dashboards = cls._list(workspace, "dashboards")
            semantic_models = cls._list(workspace, "datasets")
            dataflows = cls._list(workspace, "dataflows")
            datamarts = cls._list(workspace, "datamarts")
            summary.report_count += len(reports)
            summary.dashboard_count += len(dashboards)
            summary.semantic_model_count += len(semantic_models)
            summary.dataflow_count += len(dataflows)
            summary.datamart_count += len(datamarts)

            for semantic_model in semantic_models:
                tables = cls._list(semantic_model, "tables")
                summary.table_count += len(tables)
                summary.relationship_count += len(
                    cls._list(semantic_model, "relationships")
                )
                summary.role_count += len(cls._list(semantic_model, "roles"))
                summary.dataset_expression_count += len(
                    cls._list(semantic_model, "expressions")
                )
                for table in tables:
                    summary.column_count += len(cls._list(table, "columns"))
                    summary.measure_count += len(cls._list(table, "measures"))
                    summary.table_source_expression_count += len(
                        cls._list(table, "source")
                    )
        return summary

    @staticmethod
    def _list(
        payload: dict[str, Any],
        key: str,
        *,
        required: bool = False,
    ) -> list[dict[str, Any]]:
        value = payload.get(key)
        if value is None and not required:
            return []
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise UpstreamInvalidResponseError("powerbi")
        return value

    @classmethod
    def _required_text(
        cls,
        payload: dict[str, Any],
        key: str,
    ) -> str:
        value = cls._optional_text(payload, key)
        if value is None:
            raise UpstreamInvalidResponseError("powerbi")
        return value

    @staticmethod
    def _optional_text(
        payload: dict[str, Any],
        key: str,
    ) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise UpstreamInvalidResponseError("powerbi")
