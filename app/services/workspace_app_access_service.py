"""Everything the Power BI REST API says about one workspace app.

A workspace app (one per workspace, up to 25 audiences) is only partly
visible through Microsoft's public non-Scanner APIs:

- the app itself, its content and a flat list of who can open it come from the
  admin Apps / Reports / Dashboards APIs;
- per-object access comes from each report's or dashboard's admin users API;
- **audiences are not exposed by any API.** Their names, members and granted
  permissions only surface in ``CreateApp`` / ``UpdateApp`` activity events,
  and only for the audiences each event changed, so that reconstruction is
  opt-in and always reported as partial. Which content each audience sees is
  not available at all.

Each section degrades on its own and says so in ``coverage``; only an app that
cannot be found at all is an error.
"""

import asyncio
import json
import re
from datetime import UTC, datetime, time, timedelta
from typing import Any

from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import (
    AppException,
    ProviderResourceNotFoundError,
    ResourceNotFoundError,
)
from app.schemas.app_access import (
    AppAccessCoverage,
    AppAccessResponse,
    AppAccessWarning,
    AppAudience,
    AppObject,
    AppPrincipal,
    CoverageStatus,
)
from app.services.app_access_common import (
    MAX_PAGES,
    AdminGate,
    AdminUnavailable,
    Bounded,
    powerbi_principal,
    text,
    warn,
)
from app.services.workspace_service import WorkspaceService

APP_PAGE_SIZE = 5000
CONTENT_PAGE_SIZE = 5000
MAX_APP_PAGES = 20
MAX_AUDIENCE_HISTORY_DAYS = 28
APP_ACTIVITIES = ("CreateApp", "UpdateApp")

# "Audience name(item, item, ...)" as it appears in OrgAppPermission.
_AUDIENCE_GROUP = re.compile(r"([^()]+?)\s*\(([^()]*)\)")
_ENTIRE_ORGANIZATION = "entire organization"


class WorkspaceAppAccessService:
    def __init__(
        self,
        *,
        client: PowerBIClient | None = None,
        workspace_service: WorkspaceService | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.client = client or PowerBIClient()
        self.workspace_service = workspace_service or WorkspaceService()
        self.max_concurrency = max_concurrency

    async def build(
        self,
        *,
        app_id: str,
        access_token: str,
        audience_history_days: int = 0,
        include_object_access: bool = True,
        now: datetime | None = None,
    ) -> AppAccessResponse:
        if not 0 <= audience_history_days <= MAX_AUDIENCE_HISTORY_DAYS:
            raise ValueError("audience_history_days must be between 0 and 28.")

        warnings: list[AppAccessWarning] = []
        admin = AdminGate(label="Power BI", warnings=warnings)
        bounded = Bounded(self.max_concurrency)

        app = await self._app_metadata(
            app_id=app_id,
            access_token=access_token,
            admin=admin,
        )
        workspace_id = text(app, "workspaceId") if app else None

        (
            app_users,
            workspace_members,
            workspace_name,
            (objects, objects_status),
            audiences,
        ) = await asyncio.gather(
            self._app_users(app_id, access_token, admin, warnings),
            self._workspace_members(workspace_id, access_token, admin, warnings),
            self._workspace_name(workspace_id, access_token),
            self._objects(app_id, access_token, admin, warnings),
            self._activity_audiences(
                app_id=app_id,
                app_name=text(app, "name") if app else None,
                days=audience_history_days,
                access_token=access_token,
                admin=admin,
                bounded=bounded,
                warnings=warnings,
                now=now or datetime.now(UTC),
            ),
        )

        if app is None and app_users is None and not objects:
            # Nothing at all confirms the app exists for this caller.
            raise ResourceNotFoundError("app")

        object_access_status: CoverageStatus = "not_requested"
        if include_object_access and objects:
            await asyncio.gather(
                *(
                    bounded(
                        lambda item=item: self._object_access(
                            item,
                            access_token,
                            admin,
                        )
                    )
                    for item in objects
                )
            )
            object_access_status = _aggregate(item.access_status for item in objects)
        elif include_object_access:
            # Nothing to check when the app has no content; unknown otherwise.
            object_access_status = (
                "complete" if objects_status == "complete" else "unavailable"
            )

        warn(
            warnings,
            "WORKSPACE_APP_AUDIENCES_NOT_EXPOSED",
            "Power BI has no API for a workspace app's audiences or for the "
            "content each audience sees. "
            + (
                "Audiences below are rebuilt from CreateApp/UpdateApp activity "
                "events, which record only the audiences each event changed, "
                "name members by display name, and cover the last "
                f"{audience_history_days} day(s); audiences not changed in that "
                "window are missing."
                if audience_history_days
                else "Pass audience_history_days (1-28) to rebuild audience "
                "names and members from the activity log."
            ),
        )
        if app_users:
            warn(
                warnings,
                "WORKSPACE_USERS_NOT_IN_APP_USERS",
                "Users who already reach the app through a workspace role are "
                "not repeated in app_users; see workspace_members.",
            )

        audience_status: CoverageStatus = (
            "not_requested"
            if not audience_history_days
            else ("unavailable" if audiences is None else "partial")
        )

        return AppAccessResponse(
            app_type="workspace_app",
            app_id=app_id,
            name=text(app, "name") if app else None,
            description=text(app, "description") if app else None,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            published_by=text(app, "publishedBy") if app else None,
            last_updated=text(app, "lastUpdate") if app else None,
            app_users=app_users or [],
            workspace_members=workspace_members or [],
            audiences=audiences or [],
            objects=objects,
            coverage=AppAccessCoverage(
                app_users="complete" if app_users is not None else "unavailable",
                workspace_members=(
                    "complete" if workspace_members is not None else "unavailable"
                ),
                audiences=audience_status,
                audience_members=audience_status,
                audience_content="not_supported",
                objects=objects_status,
                object_access=object_access_status,
            ),
            warnings=warnings,
        )

    # -- App --------------------------------------------------------------

    async def _app_metadata(
        self,
        *,
        app_id: str,
        access_token: str,
        admin: AdminGate,
    ) -> dict[str, Any] | None:
        """The admin listing is the only source of the app's workspace, so it
        is tried first; the caller's installed-app view is the fallback."""
        try:
            found = await admin.call(lambda: self._find_admin_app(app_id, access_token))
        except (AdminUnavailable, AppException):
            found = None
        else:
            if found is None:
                # An administrator sees every app; absent here means absent.
                raise ResourceNotFoundError("app")
            return found

        try:
            return await self.client.get_app(app_id=app_id, access_token=access_token)
        except AppException:
            return None

    async def _find_admin_app(
        self,
        app_id: str,
        access_token: str,
    ) -> dict[str, Any] | None:
        # GetAppsAsAdmin has no single-app form; page until the app turns up.
        for page in range(MAX_APP_PAGES):
            apps = await self.client.get_apps_as_admin(
                access_token=access_token,
                top=APP_PAGE_SIZE,
                skip=page * APP_PAGE_SIZE,
            )
            for app in apps:
                if (text(app, "id") or "").casefold() == app_id.casefold():
                    return app
            if len(apps) < APP_PAGE_SIZE:
                return None
        return None

    async def _app_users(
        self,
        app_id: str,
        access_token: str,
        admin: AdminGate,
        warnings: list[AppAccessWarning],
    ) -> list[AppPrincipal] | None:
        try:
            users = await admin.call(
                lambda: self.client.get_app_users_as_admin(
                    app_id=app_id,
                    access_token=access_token,
                )
            )
        except AdminUnavailable:
            return None
        except AppException as exc:
            warn(warnings, "APP_USERS_UNAVAILABLE", exc.message)
            return None
        return [
            powerbi_principal(
                user,
                access_right_key="appUserAccessRight",
                source="GetAppUsersAsAdmin",
            )
            for user in users
        ]

    async def _workspace_members(
        self,
        workspace_id: str | None,
        access_token: str,
        admin: AdminGate,
        warnings: list[AppAccessWarning],
    ) -> list[AppPrincipal] | None:
        if workspace_id is None:
            return None
        try:
            users = await self.client.get_workspace_users(
                workspace_id=workspace_id,
                access_token=access_token,
            )
            source = "GroupsGetGroupUsers"
        except AppException:
            try:
                users = await admin.call(
                    lambda: self.client.get_workspace_users_as_admin(
                        workspace_id=workspace_id,
                        access_token=access_token,
                    )
                )
            except AdminUnavailable:
                return None
            except AppException as exc:
                warn(warnings, "WORKSPACE_MEMBERS_UNAVAILABLE", exc.message)
                return None
            source = "GetGroupUsersAsAdmin"
        return [
            powerbi_principal(
                user,
                access_right_key="groupUserAccessRight",
                source=source,
            )
            for user in users
        ]

    async def _workspace_name(
        self,
        workspace_id: str | None,
        access_token: str,
    ) -> str | None:
        if workspace_id is None:
            return None
        try:
            workspace = await self.workspace_service.get_workspace(
                workspace_id=workspace_id,
                access_token=access_token,
            )
        except AppException:
            return None
        return workspace.name

    # -- Objects ------------------------------------------------------------

    async def _objects(
        self,
        app_id: str,
        access_token: str,
        admin: AdminGate,
        warnings: list[AppAccessWarning],
    ) -> tuple[list[AppObject], CoverageStatus]:
        """The app's content: tenant-wide admin view first, then the caller's
        own view of the installed app."""
        odata_filter = f"appId eq '{app_id}'"
        results = await asyncio.gather(
            admin.call(
                lambda: self.client.get_reports_as_admin(
                    access_token=access_token,
                    odata_filter=odata_filter,
                    top=CONTENT_PAGE_SIZE,
                )
            ),
            admin.call(
                lambda: self.client.get_dashboards_as_admin(
                    access_token=access_token,
                    odata_filter=odata_filter,
                    top=CONTENT_PAGE_SIZE,
                )
            ),
            return_exceptions=True,
        )
        failures = _failures(results)
        if failures is None:
            reports, dashboards = results
            objects = _report_objects(
                reports, original_key="originalReportObjectId"
            ) + _dashboard_objects(dashboards)
            if objects:
                return objects, "complete"
            warn(
                warnings,
                "APP_CONTENT_ADMIN_EMPTY",
                "The admin report and dashboard listings returned nothing for "
                "this app; falling back to the installed app's content.",
            )
        elif failures:
            warn(warnings, "APP_CONTENT_ADMIN_UNAVAILABLE", failures[0].message)

        try:
            reports = await self.client.get_app_reports(
                app_id=app_id,
                access_token=access_token,
            )
        except AppException as exc:
            warn(warnings, "APP_CONTENT_UNAVAILABLE", exc.message)
            return [], "unavailable"

        objects = _report_objects(reports, original_key="originalReportId")
        try:
            objects += _dashboard_objects(
                await self.client.get_app_dashboards(
                    app_id=app_id,
                    access_token=access_token,
                )
            )
        except AppException as exc:
            warn(
                warnings,
                "APP_DASHBOARDS_UNAVAILABLE",
                f"The app's dashboards could not be listed: {exc.message}",
            )
        warn(
            warnings,
            "APP_CONTENT_CALLER_VIEW",
            "App content was listed from the signed-in user's view of the "
            "installed app, which may be limited to that user's audience.",
        )
        return objects, "partial"

    async def _object_access(
        self,
        item: AppObject,
        access_token: str,
        admin: AdminGate,
    ) -> None:
        """Fill in who can open one app object (mutates ``item``)."""
        is_dashboard = item.object_type == "dashboard"
        fetch_users = (
            self.client.get_dashboard_users_as_admin
            if is_dashboard
            else self.client.get_report_users_as_admin
        )
        id_key = "dashboard_id" if is_dashboard else "report_id"
        right_key = (
            "dashboardUserAccessRight" if is_dashboard else "reportUserAccessRight"
        )
        source = "GetDashboardUsersAsAdmin" if is_dashboard else "GetReportUsersAsAdmin"

        candidates = [
            (item.object_id, None),
            (
                item.workspace_object_id,
                "The app copy has no access list of its own; this is the "
                "workspace item's access.",
            ),
        ]
        for object_id, note in candidates:
            if not object_id:
                continue
            try:
                users = await admin.call(
                    lambda object_id=object_id: fetch_users(
                        **{id_key: object_id},
                        access_token=access_token,
                    )
                )
            except AdminUnavailable:
                item.access_status = "unavailable"
                item.access_note = "Needs a Power BI admin API."
                return
            except ProviderResourceNotFoundError:
                continue
            except AppException as exc:
                item.access_status = "unavailable"
                item.access_note = exc.message
                return
            item.access = [
                powerbi_principal(user, access_right_key=right_key, source=source)
                for user in users
            ]
            item.access_status = "complete"
            item.access_note = note
            return

        item.access_status = "unavailable"
        item.access_note = "Power BI did not find this object's access list."

    # -- Audiences from the activity log -----------------------------------

    async def _activity_audiences(
        self,
        *,
        app_id: str,
        app_name: str | None,
        days: int,
        access_token: str,
        admin: AdminGate,
        bounded: Bounded,
        warnings: list[AppAccessWarning],
        now: datetime,
    ) -> list[AppAudience] | None:
        if not days:
            return []

        windows = _day_windows(now, days)
        pages = await asyncio.gather(
            *(
                bounded(
                    lambda window=window, activity=activity: admin.call(
                        lambda: self._activity_day(
                            access_token=access_token,
                            window=window,
                            activity=activity,
                            warnings=warnings,
                        )
                    )
                )
                for window in windows
                for activity in APP_ACTIVITIES
            ),
            return_exceptions=True,
        )
        failures = _failures(pages)
        if failures is not None:
            if failures:
                warn(warnings, "ACTIVITY_LOG_UNAVAILABLE", failures[0].message)
            return None

        events = [
            event
            for page in pages
            for event in page
            if _is_event_for_app(event, app_id=app_id, app_name=app_name)
        ]
        if not events:
            warn(
                warnings,
                "ACTIVITY_LOG_NO_APP_EVENTS",
                f"No CreateApp or UpdateApp event for this app in the last {days} "
                "day(s), so no audience could be rebuilt.",
            )
        return audiences_from_events(events)

    async def _activity_day(
        self,
        *,
        access_token: str,
        window: tuple[str, str, bool],
        activity: str,
        warnings: list[AppAccessWarning],
    ) -> list[dict[str, Any]]:
        start, end, is_past = window
        events: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(MAX_PAGES):
            page = await self.client.get_activity_events(
                access_token=access_token,
                start_date_time=start,
                end_date_time=end,
                activity=activity,
                continuation_token=token,
                # A finished day no longer changes; today still can.
                cacheable=is_past,
            )
            events.extend(
                event
                for event in page.get("activityEventEntities") or []
                if isinstance(event, dict)
            )
            token = page.get("continuationToken")
            if page.get("lastResultSet") is True or not token:
                return events
        warn(
            warnings,
            "ACTIVITY_LOG_TRUNCATED",
            f"Stopped reading {activity} events for {start[:10]} after "
            f"{MAX_PAGES} pages.",
        )
        return events


def audiences_from_events(events: list[dict[str, Any]]) -> list[AppAudience]:
    """Latest recorded state of each audience named in app events."""
    latest: dict[str, AppAudience] = {}
    for event in sorted(events, key=lambda item: text(item, "CreationTime") or ""):
        changed_at = text(event, "CreationTime")
        for name, (recipients, permissions) in parse_org_app_permission(
            event.get("OrgAppPermission")
        ).items():
            latest[name.casefold()] = AppAudience(
                name=name,
                source="activity_log",
                members=[_recipient(recipient) for recipient in recipients],
                members_status="partial",
                permissions=permissions,
                content_status="not_supported",
                last_changed_at=changed_at,
                note=(
                    f"As recorded by a {text(event, 'Activity') or 'app'} event; "
                    "members are display names."
                ),
            )
    return sorted(latest.values(), key=lambda audience: audience.name.casefold())


def parse_org_app_permission(
    value: Any,
) -> dict[str, tuple[list[str], list[str]]]:
    """``OrgAppPermission`` -> {audience: (recipients, permissions)}.

    Documented as a string and sampled as an object of two strings, each shaped
    ``Audience(item,item)``. Both shapes are accepted; anything else yields
    nothing rather than a guess.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    if not isinstance(value, dict):
        return {}

    fields = {str(key).casefold(): item for key, item in value.items()}
    recipients = _audience_groups(fields.get("recipients"))
    permissions = _audience_groups(fields.get("permissions"))
    return {
        name: (recipients.get(name, []), permissions.get(name, []))
        for name in dict.fromkeys([*recipients, *permissions])
    }


def _audience_groups(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, str):
        return {}
    groups: dict[str, list[str]] = {}
    for match in _AUDIENCE_GROUP.finditer(value):
        name = match.group(1).strip(" ,;")
        if name:
            groups[name] = [
                part.strip() for part in match.group(2).split(",") if part.strip()
            ]
    return groups


def _recipient(name: str) -> AppPrincipal:
    return AppPrincipal(
        display_name=name,
        principal_type=(
            "EntireOrganization" if name.casefold() == _ENTIRE_ORGANIZATION else None
        ),
        source="activity_log",
    )


def _is_event_for_app(
    event: dict[str, Any],
    *,
    app_id: str,
    app_name: str | None,
) -> bool:
    event_app_id = text(event, "AppId")
    if event_app_id:
        return event_app_id.casefold() == app_id.casefold()
    # Some app events carry only the app's name.
    item_name = text(event, "ItemName")
    return bool(app_name and item_name and item_name.casefold() == app_name.casefold())


def _day_windows(now: datetime, days: int) -> list[tuple[str, str, bool]]:
    """(start, end, is_past) per UTC day; the API accepts one day per call."""
    now = now.astimezone(UTC)
    windows = []
    for offset in range(days):
        day = (now - timedelta(days=offset)).date()
        start = datetime.combine(day, time.min, tzinfo=UTC)
        end = (
            now
            if offset == 0
            else datetime.combine(day, time(23, 59, 59, 999000), tzinfo=UTC)
        )
        windows.append((_activity_time(start), _activity_time(end), offset > 0))
    return windows


def _activity_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def _report_objects(
    reports: list[dict[str, Any]],
    *,
    original_key: str,
) -> list[AppObject]:
    return [
        AppObject(
            object_id=text(report, "id"),
            workspace_object_id=text(report, original_key),
            name=text(report, "name"),
            object_type=(
                "paginated_report"
                if text(report, "reportType") == "PaginatedReport"
                else "report"
            ),
            web_url=text(report, "webUrl"),
            access_status="not_requested",
        )
        for report in reports
    ]


def _dashboard_objects(dashboards: list[dict[str, Any]]) -> list[AppObject]:
    return [
        AppObject(
            object_id=text(dashboard, "id"),
            name=text(dashboard, "displayName"),
            object_type="dashboard",
            web_url=text(dashboard, "webUrl"),
            access_status="not_requested",
        )
        for dashboard in dashboards
    ]


def _failures(results: list[Any]) -> list[AppException] | None:
    """None when every result succeeded; otherwise the provider failures
    (empty when the only failure was an admin refusal already warned about).

    Anything that is not a provider failure is a bug and is re-raised.
    """
    errors = [result for result in results if isinstance(result, BaseException)]
    if not errors:
        return None
    for error in errors:
        if not isinstance(error, (AdminUnavailable, AppException)):
            raise error
    return [error for error in errors if isinstance(error, AppException)]


def _aggregate(statuses: Any) -> CoverageStatus:
    values = set(statuses)
    if values == {"complete"}:
        return "complete"
    if "complete" in values:
        return "partial"
    return "unavailable"
