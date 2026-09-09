from datetime import UTC, datetime

import pytest

from app.schemas.scanner import ScannerWorkspaceScanRequest
from app.services.scanner_service import ScannerService

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
SCAN_ID = "22222222-2222-2222-2222-222222222222"


class FakeScannerClient:
    async def get_modified_workspaces(self, **kwargs):
        self.modified_arguments = kwargs
        return [{"id": WORKSPACE_ID}]

    async def start_workspace_scan(self, **kwargs):
        self.start_arguments = kwargs
        return {
            "id": SCAN_ID,
            "createdDateTime": "2026-09-02T10:00:00Z",
            "status": "NotStarted",
        }

    async def get_workspace_scan_status(self, **kwargs):
        self.status_arguments = kwargs
        return {
            "id": SCAN_ID,
            "createdDateTime": "2026-09-02T10:00:00Z",
            "status": "Succeeded",
        }

    async def get_workspace_scan_result(self, **kwargs):
        self.result_arguments = kwargs
        return {
            "workspaces": [
                {
                    "id": WORKSPACE_ID,
                    "reports": [{"id": "report-1"}],
                    "dashboards": [{"id": "dashboard-1"}],
                    "datasets": [
                        {
                            "id": "model-1",
                            "tables": [
                                {
                                    "name": "Sales",
                                    "columns": [{"name": "Amount"}],
                                    "measures": [{"name": "Revenue"}],
                                    "source": [{"expression": "let ..."}],
                                }
                            ],
                            "relationships": [{"name": "relationship-1"}],
                            "roles": [{"name": "Reader"}],
                            "expressions": [{"name": "Server"}],
                        }
                    ],
                    "dataflows": [{"objectId": "dataflow-1"}],
                    "datamarts": [{"id": "datamart-1"}],
                }
            ],
            "datasourceInstances": [{"datasourceId": "source-1"}],
            "misconfiguredDatasourceInstances": [{"datasourceId": "source-2"}],
        }


@pytest.mark.asyncio
async def test_list_modified_workspaces_normalizes_timestamp():
    client = FakeScannerClient()
    result = await ScannerService(client).list_modified_workspaces(
        access_token="token",
        modified_since=datetime(2026, 9, 1, tzinfo=UTC),
        exclude_personal_workspaces=True,
        exclude_inactive_workspaces=True,
    )

    assert result.count == 1
    assert str(result.workspaces[0]) == WORKSPACE_ID
    assert client.modified_arguments["modified_since"] == ("2026-09-01T00:00:00Z")


@pytest.mark.asyncio
async def test_start_and_status_map_microsoft_scan_contract():
    client = FakeScannerClient()
    service = ScannerService(client)
    request = ScannerWorkspaceScanRequest(workspaces=[WORKSPACE_ID])

    started = await service.start_scan(
        access_token="token",
        request=request,
    )
    current = await service.get_scan_status(
        access_token="token",
        scan_id=SCAN_ID,
    )

    assert str(started.scan_id) == SCAN_ID
    assert started.status == "NotStarted"
    assert current.status == "Succeeded"
    assert client.start_arguments["dataset_expressions"] is True


@pytest.mark.asyncio
async def test_scan_result_preserves_payload_and_builds_summary():
    client = FakeScannerClient()
    result = await ScannerService(client).get_scan_result(
        access_token="token",
        scan_id=SCAN_ID,
    )

    assert result.payload["workspaces"][0]["datasets"][0]["id"] == ("model-1")
    assert result.summary.workspace_count == 1
    assert result.summary.report_count == 1
    assert result.summary.semantic_model_count == 1
    assert result.summary.table_count == 1
    assert result.summary.column_count == 1
    assert result.summary.measure_count == 1
    assert result.summary.datasource_instance_count == 1
    assert result.summary.misconfigured_datasource_instance_count == 1
