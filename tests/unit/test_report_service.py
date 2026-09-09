from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import UpstreamInvalidResponseError
from app.services.report_service import ReportService


@pytest.mark.asyncio
async def test_list_reports_maps_powerbi_response():
    service = ReportService()

    service.client.get_reports_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "report-1",
                "name": "Sales Analysis",
                "datasetId": "dataset-1",
                "reportType": "PowerBIReport",
                "format": "PBIR",
                "webUrl": "https://app.powerbi.com/report-1",
                "isOwnedByMe": True,
            }
        ]
    )

    result = await service.list_reports(
        workspace_id="workspace-1",
        access_token="fake-token",
    )

    assert result.workspace_id == "workspace-1"
    assert result.count == 1

    report = result.reports[0]

    assert report.id == "report-1"
    assert report.name == "Sales Analysis"
    assert report.dataset_id == "dataset-1"
    assert report.report_type == "PowerBIReport"
    assert report.format == "PBIR"
    assert report.web_url == "https://app.powerbi.com/report-1"
    assert report.is_owned_by_me is True


@pytest.mark.asyncio
async def test_list_reports_allows_missing_dataset_id():
    service = ReportService()

    service.client.get_reports_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "report-1",
                "name": "Paginated Report",
                "reportType": "PaginatedReport",
            }
        ]
    )

    result = await service.list_reports(
        workspace_id="workspace-1",
        access_token="fake-token",
    )

    assert result.count == 1

    report = result.reports[0]

    assert report.id == "report-1"
    assert report.name == "Paginated Report"
    assert report.dataset_id is None


@pytest.mark.asyncio
async def test_list_reports_handles_empty_workspace():
    service = ReportService()

    service.client.get_reports_in_workspace = AsyncMock(return_value=[])

    result = await service.list_reports(
        workspace_id="workspace-1",
        access_token="fake-token",
    )

    assert result.workspace_id == "workspace-1"
    assert result.count == 0
    assert result.reports == []


@pytest.mark.asyncio
async def test_report_missing_id_raises_invalid_response():
    service = ReportService()

    service.client.get_reports_in_workspace = AsyncMock(
        return_value=[
            {
                "name": "Sales Analysis",
                "datasetId": "dataset-1",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_reports(
            workspace_id="workspace-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_report_missing_name_raises_invalid_response():
    service = ReportService()

    service.client.get_reports_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "report-1",
                "datasetId": "dataset-1",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_reports(
            workspace_id="workspace-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_report_empty_id_raises_invalid_response():
    service = ReportService()

    service.client.get_reports_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "",
                "name": "Sales Analysis",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_reports(
            workspace_id="workspace-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_report_empty_name_raises_invalid_response():
    service = ReportService()

    service.client.get_reports_in_workspace = AsyncMock(
        return_value=[
            {
                "id": "report-1",
                "name": "",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_reports(
            workspace_id="workspace-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_get_report_maps_report_detail():
    service = ReportService()

    service.client.get_report = AsyncMock(
        return_value={
            "id": "report-1",
            "name": "Sales Report",
            "datasetId": "dataset-1",
            "description": "Executive sales report",
            "reportType": "PowerBIReport",
            "format": "PBIR",
            "webUrl": ("https://app.powerbi.com/report-1"),
            "isOwnedByMe": True,
        }
    )

    result = await service.get_report(
        workspace_id="workspace-1",
        report_id="report-1",
        access_token="fake-token",
    )

    assert result.id == "report-1"
    assert result.name == "Sales Report"
    assert result.dataset_id == "dataset-1"
    assert result.description == "Executive sales report"
    assert result.report_type == "PowerBIReport"
    assert result.format == "PBIR"
    assert result.is_owned_by_me is True


@pytest.mark.asyncio
async def test_get_my_workspace_report_maps_report_detail():
    service = ReportService()

    service.client.get_report_in_my_workspace = AsyncMock(
        return_value={
            "id": "report-1",
            "name": "My Workspace Sales Report",
            "datasetId": "dataset-1",
            "reportType": "PowerBIReport",
        }
    )

    result = await service.get_my_workspace_report(
        report_id="report-1",
        access_token="fake-token",
    )

    assert result.id == "report-1"
    assert result.name == "My Workspace Sales Report"
    service.client.get_report_in_my_workspace.assert_awaited_once_with(
        report_id="report-1",
        access_token="fake-token",
    )


@pytest.mark.asyncio
async def test_list_pages_maps_pages():
    service = ReportService()

    service.client.get_report_pages = AsyncMock(
        return_value=[
            {
                "name": "ReportSection2",
                "displayName": "Regional Sales",
                "order": "1",
            },
            {
                "name": "ReportSection",
                "displayName": "Executive Summary",
                "order": "0",
            },
        ]
    )

    result = await service.list_pages(
        workspace_id="workspace-1",
        report_id="report-1",
        access_token="fake-token",
    )

    assert result.workspace_id == "workspace-1"
    assert result.report_id == "report-1"
    assert result.count == 2

    assert result.pages[0].name == "ReportSection"

    assert result.pages[0].display_name == "Executive Summary"

    assert result.pages[0].order == 0

    assert result.pages[1].name == "ReportSection2"

    assert result.pages[1].order == 1


@pytest.mark.asyncio
async def test_list_pages_handles_empty_report():
    service = ReportService()

    service.client.get_report_pages = AsyncMock(return_value=[])

    result = await service.list_pages(
        workspace_id="workspace-1",
        report_id="report-1",
        access_token="fake-token",
    )

    assert result.count == 0
    assert result.pages == []


@pytest.mark.asyncio
async def test_get_single_page():
    service = ReportService()

    service.client.get_report_page = AsyncMock(
        return_value={
            "name": "ReportSection",
            "displayName": "Executive Summary",
            "order": 0,
        }
    )

    result = await service.get_page(
        workspace_id="workspace-1",
        report_id="report-1",
        page_name="ReportSection",
        access_token="fake-token",
    )

    assert result.name == "ReportSection"

    assert result.display_name == "Executive Summary"

    assert result.order == 0


@pytest.mark.asyncio
async def test_page_missing_name_raises_invalid_response():
    service = ReportService()

    service.client.get_report_pages = AsyncMock(
        return_value=[
            {
                "displayName": "Executive Summary",
                "order": 0,
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_pages(
            workspace_id="workspace-1",
            report_id="report-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_page_missing_display_name_raises_invalid_response():
    service = ReportService()

    service.client.get_report_pages = AsyncMock(
        return_value=[
            {
                "name": "ReportSection",
                "order": 0,
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_pages(
            workspace_id="workspace-1",
            report_id="report-1",
            access_token="fake-token",
        )


@pytest.mark.asyncio
async def test_invalid_page_order_raises_invalid_response():
    service = ReportService()

    service.client.get_report_pages = AsyncMock(
        return_value=[
            {
                "name": "ReportSection",
                "displayName": "Executive Summary",
                "order": "invalid",
            }
        ]
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.list_pages(
            workspace_id="workspace-1",
            report_id="report-1",
            access_token="fake-token",
        )
