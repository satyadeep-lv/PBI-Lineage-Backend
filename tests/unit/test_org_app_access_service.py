import base64
import json
from collections import Counter

import httpx
import pytest

from app.core.exceptions import InsufficientPermissionsError
from app.services.fabric_item_definition_service import FabricItemDefinitionReader
from app.services.org_app_access_service import OrgAppAccessService

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
APP_ID = "22222222-2222-2222-2222-222222222222"
LOGICAL_ID = "33333333-3333-3333-3333-333333333333"
REPORT_ID = "44444444-4444-4444-4444-444444444444"
DASHBOARD_ID = "55555555-5555-5555-5555-555555555555"


def _definition(parts: dict[str, dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "definition": {
                "parts": [
                    {
                        "path": path,
                        "payload": base64.b64encode(
                            json.dumps(content).encode()
                        ).decode(),
                        "payloadType": "InlineBase64",
                    }
                    for path, content in parts.items()
                ]
            }
        },
    )


APP_DEFINITION = {
    "definition.json": {
        "settings": {"audienceSettings": {"hideAudienceTabs": False}},
        "elements": [
            {"elementType": "overview", "elementId": "e-overview"},
            {
                "elementType": "section",
                "elementId": "e-section",
                "displayName": "Finance",
                "elements": [
                    {
                        "elementType": "item",
                        "elementId": "e-report",
                        "itemId": REPORT_ID,
                        "itemType": "Report",
                    },
                    {
                        "elementType": "item",
                        "elementId": "e-dashboard",
                        "itemId": DASHBOARD_ID,
                        "itemType": "Dashboard",
                        "isHidden": True,
                    },
                ],
            },
            {
                "elementType": "link",
                "elementId": "e-link",
                "displayName": "Wiki",
                "url": "https://wiki.example.com",
            },
        ],
    },
    ".platform": {"config": {"logicalId": LOGICAL_ID}},
}


def _audience(parent: str, references: list[dict], *, hidden_access=False) -> dict:
    return {
        "definition.json": {
            "parentAppId": parent,
            "settings": {"hasAccessToHiddenContent": hidden_access},
            "elementReferences": references,
        }
    }


AUDIENCE_DEFINITIONS = {
    "aud-finance": _audience(
        LOGICAL_ID,
        [
            {"elementId": "e-report", "itemId": REPORT_ID, "itemType": "Report"},
            {"elementId": "e-dashboard", "isElementHidden": True},
        ],
    ),
    "aud-execs": _audience(
        LOGICAL_ID,
        [{"elementId": "e-dashboard", "itemId": DASHBOARD_ID}],
        hidden_access=True,
    ),
    # Belongs to a different org app in the same workspace.
    "aud-other": _audience("99999999-9999-9999-9999-999999999999", []),
}


class _Fabric:
    def __init__(
        self,
        *,
        admin: bool = True,
        unreadable=(),
        item_logical_id: str | None = None,
    ) -> None:
        self.admin = admin
        self.item_logical_id = item_logical_id
        self.unreadable = set(unreadable)
        self.calls: Counter = Counter()
        self.access_types: dict[str, str | None] = {}

    async def get_org_app(self, *, workspace_id, org_app_id, access_token):
        # By default no logicalId on the item, so it comes from .platform.
        item = {"id": org_app_id, "displayName": "Finance App"}
        if self.item_logical_id:
            item["logicalId"] = self.item_logical_id
        return item

    async def get_workspace(self, *, workspace_id, access_token):
        return {"id": workspace_id, "displayName": "Finance WS"}

    async def start_org_app_definition(self, *, workspace_id, org_app_id, access_token):
        if "app" in self.unreadable:
            raise InsufficientPermissionsError("fabric")
        return _definition(APP_DEFINITION)

    async def list_org_app_audiences(
        self,
        *,
        workspace_id,
        access_token,
        continuation_token=None,
    ):
        if continuation_token is None:
            return {
                "value": [{"id": "aud-finance", "displayName": "Finance"}],
                "continuationToken": "page-2",
            }
        return {
            "value": [
                {"id": "aud-execs", "displayName": "Execs"},
                {"id": "aud-other", "displayName": "Someone else's"},
            ]
        }

    async def start_org_app_audience_definition(
        self,
        *,
        workspace_id,
        audience_id,
        access_token,
    ):
        if audience_id in self.unreadable:
            raise InsufficientPermissionsError("fabric")
        return _definition(AUDIENCE_DEFINITIONS[audience_id])

    async def list_items(self, *, workspace_id, access_token, continuation_token=None):
        return {
            "value": [
                {"id": REPORT_ID, "displayName": "Revenue", "type": "Report"},
                {"id": DASHBOARD_ID, "displayName": "KPIs", "type": "Dashboard"},
            ]
        }

    async def list_workspace_role_assignments(
        self,
        *,
        workspace_id,
        access_token,
        continuation_token=None,
    ):
        return {
            "value": [
                {
                    "principal": {
                        "id": "owner-1",
                        "displayName": "Owner",
                        "type": "User",
                        "userDetails": {"userPrincipalName": "owner@example.com"},
                    },
                    "role": "Admin",
                }
            ]
        }

    async def list_item_access_details_as_admin(
        self,
        *,
        workspace_id,
        item_id,
        access_token,
        item_type=None,
    ):
        self.calls["admin"] += 1
        if not self.admin:
            raise InsufficientPermissionsError("fabric")
        self.access_types[item_id] = item_type
        return {
            "accessDetails": [
                {
                    "principal": {
                        "id": f"principal-{item_id}",
                        "displayName": f"Group for {item_id}",
                        "type": "Group",
                    },
                    "itemAccessDetails": {
                        "type": item_type or "OrgAppAudience",
                        "permissions": ["Read", "Reshare"],
                        "additionalPermissions": ["ReadAll"],
                    },
                }
            ]
        }


def _service(client: _Fabric) -> OrgAppAccessService:
    return OrgAppAccessService(client=client)


async def _build(client: _Fabric, **options):
    return await _service(client).build(
        workspace_id=WORKSPACE_ID,
        org_app_id=APP_ID,
        access_token="token",
        **options,
    )


def _codes(response) -> set[str]:
    return {warning.code for warning in response.warnings}


@pytest.mark.asyncio
async def test_org_app_maps_audiences_to_content_members_and_objects():
    client = _Fabric()

    response = await _build(client)

    assert response.app_type == "org_app"
    assert response.name == "Finance App"
    assert response.workspace_name == "Finance WS"
    assert response.logical_id == LOGICAL_ID

    audiences = {audience.name: audience for audience in response.audiences}
    # The audience whose parentAppId names another app is left out.
    assert set(audiences) == {"Finance", "Execs"}
    finance = audiences["Finance"]
    assert [(c.name, c.visible) for c in finance.content] == [
        ("Revenue", True),
        ("KPIs", False),
    ]
    assert finance.members[0].display_name == "Group for aud-finance"
    assert finance.members[0].permissions == ["Read", "Reshare", "ReadAll"]
    assert audiences["Execs"].has_access_to_hidden_content is True

    objects = {item.name: item for item in response.objects}
    assert set(objects) == {"Revenue", "KPIs", "Wiki"}
    assert objects["Revenue"].audiences == ["Finance"]
    assert objects["KPIs"].audiences == ["Execs"]
    assert objects["KPIs"].hidden_in_navigation is True
    assert objects["Revenue"].access[0].id == f"principal-{REPORT_ID}"
    # The item type is passed, as the API requires for reports and dashboards.
    assert client.access_types[REPORT_ID] == "Report"
    assert client.access_types[DASHBOARD_ID] == "Dashboard"
    assert objects["Wiki"].object_type == "link"
    assert objects["Wiki"].access_status == "not_supported"

    assert response.app_users[0].id == f"principal-{APP_ID}"
    assert response.workspace_members[0].email == "owner@example.com"
    assert response.workspace_members[0].access_right == "Admin"

    assert set(response.coverage.model_dump().values()) == {"complete"}
    assert {
        "ORG_APP_HIDDEN_CONTENT_SHARED",
        "ORG_APP_AUDIENCE_MEMBERS_INFERRED",
        "WORKSPACE_MEMBERS_SEE_ALL_AUDIENCES",
    } <= _codes(response)


@pytest.mark.asyncio
async def test_without_admin_rights_content_is_kept_and_access_marked_unavailable():
    client = _Fabric(admin=False)

    response = await _build(client)

    # The first refusal closes the gate; no other admin call is attempted.
    assert client.calls["admin"] == 1
    assert [w.code for w in response.warnings].count("ADMIN_API_UNAVAILABLE") == 1
    assert response.coverage.app_users == "unavailable"
    assert response.coverage.audience_members == "unavailable"
    assert response.coverage.object_access == "unavailable"
    assert response.coverage.audience_content == "complete"
    assert {audience.name for audience in response.audiences} == {"Finance", "Execs"}
    assert all(not audience.members for audience in response.audiences)


@pytest.mark.asyncio
async def test_unreadable_definitions_degrade_instead_of_failing():
    client = _Fabric(unreadable={"app", "aud-execs"}, item_logical_id=LOGICAL_ID)

    response = await _build(client, include_member_access=False)

    assert response.objects == []
    assert response.coverage.objects == "unavailable"
    assert response.coverage.object_access == "unavailable"
    assert response.coverage.audiences == "partial"
    assert response.coverage.audience_members == "not_requested"
    assert [audience.name for audience in response.audiences] == ["Finance"]
    # Content is still listed, named from the workspace items.
    assert response.audiences[0].content[0].name == "Revenue"
    assert {"ORG_APP_DEFINITION_UNAVAILABLE", "ORG_APP_AUDIENCE_UNATTRIBUTED"} <= (
        _codes(response)
    )


@pytest.mark.asyncio
async def test_unknown_logical_id_marks_audiences_unattributed_not_foreign():
    # Neither the item nor a readable definition carries the logical ID.
    client = _Fabric(unreadable={"app"})

    response = await _build(client, include_member_access=False)

    assert response.audiences == []
    assert response.coverage.audiences == "partial"
    assert {"ORG_APP_LOGICAL_ID_UNKNOWN", "ORG_APP_AUDIENCE_UNATTRIBUTED"} <= (
        _codes(response)
    )


@pytest.mark.asyncio
async def test_definition_reader_polls_a_long_running_operation(monkeypatch):
    sleeps: list[int] = []

    async def no_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(
        "app.services.fabric_item_definition_service.asyncio.sleep",
        no_sleep,
    )

    class _Operations:
        def __init__(self) -> None:
            self.states = iter(["Running", "Succeeded"])

        async def get_operation_state(self, *, operation_id, access_token):
            assert operation_id == "op-1"
            return httpx.Response(
                200,
                json={"status": next(self.states)},
                headers={"Retry-After": "3"},
            )

        async def get_operation_result(self, *, operation_id, access_token):
            return _definition({"definition.json": {"parentAppId": "x"}})

    async def start():
        return httpx.Response(202, headers={"x-ms-operation-id": "op-1"})

    parts = await FabricItemDefinitionReader(_Operations()).read_json_parts(
        cache_key=("test", "op"),
        start=start,
        access_token="token",
    )

    assert parts == {"definition.json": {"parentAppId": "x"}}
    assert sleeps == [2, 3]
