from typing import Any

from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import UpstreamInvalidResponseError
from app.schemas.report import (
    Report,
    ReportListResponse,
    ReportUserListResponse,
    ReportUser
)
from app.schemas.report_page import (
    ReportPage,
    ReportPageListResponse,
)


class ReportService:
    def __init__(self) -> None:
        self.client = PowerBIClient()

    async def get_report_users(
        self,
        *,
        report_id: str,
        workspace_id: str | None = None,
        access_token: str,
    ) -> ReportUserListResponse:
        
        raw_users = None

        # 1. Try the workspace endpoint first if we have a workspace_id
        if workspace_id:
            try:
                raw_users = await self.client.get_report_users_in_workspace(
                    workspace_id=workspace_id,
                    report_id=report_id,
                    access_token=access_token,
                )
            except Exception:
                # If provider_get raises an error (like 404 FeatureNotAvailable),
                # we catch it and do nothing, allowing it to fall through to the admin endpoint.
                raw_users = None

        # 2. Fallback to admin endpoint if workspace_id was missing OR the workspace call failed
        if raw_users is None:
            raw_users = await self.client.get_report_users_as_admin(
                report_id=report_id,
                access_token=access_token,
            )

        users = [self._map_report_user(user) for user in raw_users]

        return ReportUserListResponse(
            report_id=report_id,
            users=users,
            count=len(users),
        )

    async def list_reports(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> ReportListResponse:
        raw_reports = await self.client.get_reports_in_workspace(
            workspace_id=workspace_id,
            access_token=access_token,
        )

        reports = [self._map_report(report) for report in raw_reports]

        return ReportListResponse(
            workspace_id=workspace_id,
            reports=reports,
            count=len(reports),
        )

    async def get_report(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
    ) -> Report:
        raw_report = await self.client.get_report(
            workspace_id=workspace_id,
            report_id=report_id,
            access_token=access_token,
        )

        return self._map_report(raw_report)

    async def get_my_workspace_report(
        self,
        *,
        report_id: str,
        access_token: str,
    ) -> Report:
        raw_report = await self.client.get_report_in_my_workspace(
            report_id=report_id,
            access_token=access_token,
        )

        return self._map_report(raw_report)

    async def list_pages(
        self,
        *,
        workspace_id: str,
        report_id: str,
        access_token: str,
    ) -> ReportPageListResponse:
        raw_pages = await self.client.get_report_pages(
            workspace_id=workspace_id,
            report_id=report_id,
            access_token=access_token,
        )

        pages = [self._map_page(page) for page in raw_pages]

        pages.sort(key=lambda page: page.order)

        return ReportPageListResponse(
            workspace_id=workspace_id,
            report_id=report_id,
            pages=pages,
            count=len(pages),
        )

    async def get_page(
        self,
        *,
        workspace_id: str,
        report_id: str,
        page_name: str,
        access_token: str,
    ) -> ReportPage:
        raw_page = await self.client.get_report_page(
            workspace_id=workspace_id,
            report_id=report_id,
            page_name=page_name,
            access_token=access_token,
        )

        return self._map_page(raw_page)

    @staticmethod
    def _map_report(
        report: dict[str, Any],
    ) -> Report:
        report_id = report.get("id")
        report_name = report.get("name")

        if not isinstance(report_id, str) or not report_id:
            raise UpstreamInvalidResponseError("powerbi")

        if not isinstance(report_name, str) or not report_name:
            raise UpstreamInvalidResponseError("powerbi")

        return Report(
            id=report_id,
            name=report_name,
            dataset_id=report.get("datasetId"),
            description=report.get("description"),
            report_type=report.get("reportType"),
            format=report.get("format"),
            web_url=report.get("webUrl"),
            is_owned_by_me=report.get("isOwnedByMe"),
        )

    @staticmethod
    def _map_page(
        page: dict[str, Any],
    ) -> ReportPage:
        page_name = page.get("name")
        display_name = page.get("displayName")
        raw_order = page.get("order")

        if not isinstance(page_name, str) or not page_name:
            raise UpstreamInvalidResponseError("powerbi")

        if not isinstance(display_name, str) or not display_name:
            raise UpstreamInvalidResponseError("powerbi")

        if isinstance(raw_order, bool):
            raise UpstreamInvalidResponseError("powerbi")

        try:
            order = int(raw_order)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise UpstreamInvalidResponseError("powerbi") from exc

        if order < 0:
            raise UpstreamInvalidResponseError("powerbi")

        return ReportPage(
            name=page_name,
            display_name=display_name,
            order=order,
        )
    @staticmethod
    def _map_report_user(
        user: dict[str, Any],
    ) -> ReportUser:
        identifier = user.get("identifier")

        if not isinstance(identifier, str) or not identifier:
            raise UpstreamInvalidResponseError("powerbi")

        return ReportUser(
            identifier=identifier,
            principal_type=user.get("principalType"),
            email_address=user.get("emailAddress"),
            display_name=user.get("displayName"),
            user_right=user.get("reportUserAccessRight") or user.get("userRight"),
        )
