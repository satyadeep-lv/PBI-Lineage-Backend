from collections import Counter
from datetime import UTC, datetime

import pytest

from app.core.exceptions import (
    InsufficientPermissionsError,
    ProviderResourceNotFoundError,
    ResourceNotFoundError,
)
from app.schemas.workspace import Workspace
from app.services.workspace_app_access_service import (
    WorkspaceAppAccessService,
    audiences_from_events,
    parse_org_app_permission,
)

APP_ID = "0a1b2c3d-0000-4000-8000-000000000001"
OTHER_APP_ID = "0a1b2c3d-0000-4000-8000-000000000099"
WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 9, 29, 10, 30, tzinfo=UTC)

APP = {
    "id": APP_ID,
    "name": "Sales App",
    "description": "Regional sales",
    "publishedBy": "Publisher",
    "lastUpdate": "2026-09-20T08:00:00Z",
    "workspaceId": WORKSPACE_ID,
}


class _PowerBI:
    """Fake Power BI client; ``admin=False`` refuses every admin API."""

    def __init__(self, *, admin: bool = True, events=None) -> None:
        self.admin = admin
        self.calls: Counter = Counter()
        self.activity_requests: list[dict] = []
        self.events = events or {}

    def _admin(self, name: str) -> None:
        self.calls[name] += 1
        if not self.admin:
            raise InsufficientPermissionsError("powerbi")

    async def get_apps_as_admin(self, *, access_token, top, skip):
        self._admin("admin_apps")
        return [{"id": OTHER_APP_ID, "name": "Other"}, APP]

    async def get_app(self, *, app_id, access_token):
        self.calls["app"] += 1
        return {key: value for key, value in APP.items() if key != "workspaceId"}

    async def get_app_users_as_admin(self, *, app_id, access_token):
        self._admin("app_users")
        return [
            {
                "displayName": "Sales Readers",
                "identifier": "group-1",
                "graphId": "graph-group-1",
                "principalType": "Group",
                "appUserAccessRight": "ReadExplore",
            },
            {"principalType": "None", "appUserAccessRight": "Read"},
        ]

    async def get_reports_as_admin(self, *, access_token, odata_filter, top):
        self._admin("admin_reports")
        assert odata_filter == f"appId eq '{APP_ID}'"
        return [
            {
                "id": "app-report-1",
                "name": "[App] Revenue",
                "appId": APP_ID,
                "originalReportObjectId": "ws-report-1",
                "reportType": "PowerBIReport",
                "webUrl": "https://app.powerbi.com/r1",
            },
            {
                "id": "app-report-2",
                "name": "[App] Invoices",
                "appId": APP_ID,
                "originalReportObjectId": "ws-report-2",
                "reportType": "PaginatedReport",
            },
        ]

    async def get_dashboards_as_admin(self, *, access_token, odata_filter, top):
        self._admin("admin_dashboards")
        return [{"id": "app-dash-1", "displayName": "KPIs", "appId": APP_ID}]

    async def get_app_reports(self, *, app_id, access_token):
        self.calls["app_reports"] += 1
        return [
            {
                "id": "app-report-1",
                "name": "[App] Revenue",
                "originalReportId": "ws-report-1",
            }
        ]

    async def get_app_dashboards(self, *, app_id, access_token):
        self.calls["app_dashboards"] += 1
        raise InsufficientPermissionsError("powerbi")

    async def get_report_users_as_admin(self, *, report_id, access_token):
        self._admin(f"report_users:{report_id}")
        if report_id == "app-report-2":
            raise ProviderResourceNotFoundError("powerbi", "report")
        return [
            {
                "displayName": "Ana",
                "emailAddress": "ana@example.com",
                "principalType": "User",
                "reportUserAccessRight": "Read",
            }
        ]

    async def get_dashboard_users_as_admin(self, *, dashboard_id, access_token):
        self._admin("dashboard_users")
        return [{"displayName": "Ops", "dashboardUserAccessRight": "ReadReshare"}]

    async def get_workspace_users(self, *, workspace_id, access_token):
        self.calls["workspace_users"] += 1
        return [
            {
                "displayName": "Owner",
                "emailAddress": "owner@example.com",
                "principalType": "User",
                "groupUserAccessRight": "Admin",
            }
        ]

    async def get_workspace_users_as_admin(self, *, workspace_id, access_token):
        self._admin("admin_workspace_users")
        return []

    async def get_activity_events(
        self,
        *,
        access_token,
        start_date_time,
        end_date_time,
        activity,
        continuation_token=None,
        cacheable=False,
    ):
        self._admin("activity")
        self.activity_requests.append(
            {
                "start": start_date_time,
                "end": end_date_time,
                "activity": activity,
                "token": continuation_token,
                "cacheable": cacheable,
            }
        )
        pages = self.events.get((start_date_time[:10], activity), [[]])
        index = int(continuation_token or 0)
        return {
            "activityEventEntities": pages[index],
            "continuationToken": (str(index + 1) if index + 1 < len(pages) else None),
        }


class _Workspaces:
    async def get_workspace(self, *, workspace_id, access_token):
        return Workspace(id=workspace_id, name="Sales Workspace")


def _service(client: _PowerBI) -> WorkspaceAppAccessService:
    return WorkspaceAppAccessService(client=client, workspace_service=_Workspaces())


def _codes(response) -> set[str]:
    return {warning.code for warning in response.warnings}


@pytest.mark.asyncio
async def test_admin_session_returns_app_users_objects_and_object_access():
    client = _PowerBI()

    response = await _service(client).build(
        app_id=APP_ID,
        access_token="token",
        now=NOW,
    )

    assert response.app_type == "workspace_app"
    assert response.name == "Sales App"
    assert response.workspace_id == WORKSPACE_ID
    assert response.workspace_name == "Sales Workspace"
    assert response.published_by == "Publisher"

    group, organization = response.app_users
    assert (group.id, group.principal_type, group.access_right) == (
        "graph-group-1",
        "Group",
        "ReadExplore",
    )
    assert organization.principal_type == "EntireOrganization"
    assert response.workspace_members[0].access_right == "Admin"

    by_id = {item.object_id: item for item in response.objects}
    assert by_id["app-report-1"].workspace_object_id == "ws-report-1"
    assert by_id["app-report-2"].object_type == "paginated_report"
    assert by_id["app-dash-1"].object_type == "dashboard"
    assert by_id["app-report-1"].access[0].email == "ana@example.com"
    # The app copy had no access list, so the workspace report's is used.
    assert client.calls["report_users:ws-report-2"] == 1
    assert "workspace item" in by_id["app-report-2"].access_note
    assert by_id["app-dash-1"].access[0].access_right == "ReadReshare"

    assert response.coverage.model_dump() == {
        "app_users": "complete",
        "workspace_members": "complete",
        "audiences": "not_requested",
        "audience_members": "not_requested",
        "audience_content": "not_supported",
        "objects": "complete",
        "object_access": "complete",
    }
    assert "WORKSPACE_APP_AUDIENCES_NOT_EXPOSED" in _codes(response)
    assert client.calls["activity"] == 0


@pytest.mark.asyncio
async def test_audiences_are_rebuilt_from_activity_events():
    create = {
        "Activity": "CreateApp",
        "AppId": APP_ID,
        "CreationTime": "2026-09-28T09:00:00Z",
        "OrgAppPermission": {
            "recipients": (
                "Sales Reps(North America,Europe), Execs(Entire Organization)"
            ),
            "permissions": "Sales Reps(Read,CopyOnWrite), Execs(Read)",
        },
    }
    update = {
        "Activity": "UpdateApp",
        "AppId": APP_ID,
        "CreationTime": "2026-09-29T08:00:00Z",
        "OrgAppPermission": '{"recipients": "Sales Reps(Europe)", '
        '"permissions": "Sales Reps(Read)"}',
    }
    other_app = {**create, "AppId": OTHER_APP_ID}
    client = _PowerBI(
        events={
            ("2026-09-28", "CreateApp"): [[other_app], [create]],
            ("2026-09-29", "UpdateApp"): [[update]],
        }
    )

    response = await _service(client).build(
        app_id=APP_ID,
        access_token="token",
        audience_history_days=2,
        include_object_access=False,
        now=NOW,
    )

    audiences = {audience.name: audience for audience in response.audiences}
    assert set(audiences) == {"Sales Reps", "Execs"}
    # The later UpdateApp wins for the audience it changed.
    assert [member.display_name for member in audiences["Sales Reps"].members] == [
        "Europe"
    ]
    assert audiences["Sales Reps"].permissions == ["Read"]
    assert audiences["Execs"].members[0].principal_type == "EntireOrganization"
    assert audiences["Execs"].source == "activity_log"
    assert response.coverage.audiences == "partial"
    assert response.coverage.audience_content == "not_supported"
    assert response.coverage.object_access == "not_requested"

    # Today's window ends now and is never cached; finished days are.
    today = [r for r in client.activity_requests if r["start"].startswith("2026-09-29")]
    assert today[0]["end"] == "2026-09-29T10:30:00.000Z"
    assert all(not request["cacheable"] for request in today)
    assert all(
        request["cacheable"]
        for request in client.activity_requests
        if request["start"].startswith("2026-09-28")
    )
    # Two days x two activities, plus one continuation page.
    assert client.calls["activity"] == 5


@pytest.mark.asyncio
async def test_non_admin_session_stops_calling_admin_apis_after_one_refusal():
    client = _PowerBI(admin=False)

    response = await _service(client).build(
        app_id=APP_ID,
        access_token="token",
        audience_history_days=3,
        now=NOW,
    )

    admin_calls = sum(
        count
        for name, count in client.calls.items()
        if name.startswith(("admin", "app_users", "report_users", "activity"))
    )
    assert admin_calls == 1
    assert [w.code for w in response.warnings].count("ADMIN_API_UNAVAILABLE") == 1

    assert response.name == "Sales App"
    assert response.workspace_id is None
    assert [item.object_id for item in response.objects] == ["app-report-1"]
    assert response.objects[0].access_status == "unavailable"
    assert response.coverage.app_users == "unavailable"
    assert response.coverage.objects == "partial"
    assert response.coverage.audiences == "unavailable"
    assert response.coverage.object_access == "unavailable"
    assert "APP_CONTENT_CALLER_VIEW" in _codes(response)


@pytest.mark.asyncio
async def test_app_missing_from_the_admin_listing_is_not_found():
    with pytest.raises(ResourceNotFoundError):
        await _service(_PowerBI()).build(
            app_id="0a1b2c3d-0000-4000-8000-00000000dead",
            access_token="token",
        )


def test_org_app_permission_accepts_documented_shapes_and_rejects_others():
    assert parse_org_app_permission(
        {"recipients": "A(x,y)", "permissions": "A(Read)"}
    ) == {"A": (["x", "y"], ["Read"])}
    assert parse_org_app_permission('{"Recipients": "B(z)"}') == {"B": (["z"], [])}
    assert parse_org_app_permission("not json") == {}
    assert parse_org_app_permission(None) == {}
    assert audiences_from_events([{"OrgAppPermission": 42}]) == []
