"""Everything the Fabric REST API says about one org app.

Org apps (several per workspace) model audiences as their own items, so far
more is documented than for workspace apps:

- the org app definition lists the app's content (``elements``);
- each ``OrgAppAudience`` definition names its parent app (``parentAppId``,
  matched against the app's logical ID) and which of those elements the
  audience sees (``elementReferences[].isElementHidden``);
- who is in an audience is not in any definition. Microsoft documents that
  audience membership is managed as permissions on the audience item, so it is
  read with the Fabric admin "List Item Access Details" API on the audience --
  an inference the docs do not state outright, flagged in a warning.

Definitions need read *and* write permission on the item even though they are
only read; the admin reads need a Fabric administrator or service principal.
Each section degrades on its own; only an org app that cannot be read is an
error.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.clients.fabric_client import FabricClient
from app.core.exceptions import AppException
from app.schemas.app_access import (
    AppAccessCoverage,
    AppAccessResponse,
    AppAccessWarning,
    AppAudience,
    AppAudienceContent,
    AppObject,
    AppPrincipal,
    CoverageStatus,
)
from app.services.app_access_common import (
    AdminGate,
    AdminUnavailable,
    Bounded,
    collect_pages,
    fabric_access_details,
    fabric_principal,
    text,
    warn,
)
from app.services.fabric_item_definition_service import FabricItemDefinitionReader

DEFINITION_PART = "definition.json"
PLATFORM_PART = ".platform"
ITEM_ELEMENT = "item"
LINK_ELEMENT = "link"
ACCESS_SOURCE = "Fabric ListItemAccessDetails"


class OrgAppAccessService:
    def __init__(
        self,
        *,
        client: FabricClient | None = None,
        definition_reader: FabricItemDefinitionReader | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.client = client or FabricClient()
        self.definition_reader = definition_reader or FabricItemDefinitionReader(
            self.client
        )
        self.max_concurrency = max_concurrency

    async def build(
        self,
        *,
        workspace_id: str,
        org_app_id: str,
        access_token: str,
        include_member_access: bool = True,
        include_object_access: bool = True,
    ) -> AppAccessResponse:
        warnings: list[AppAccessWarning] = []
        admin = AdminGate(label="Fabric", warnings=warnings)
        bounded = Bounded(self.max_concurrency)

        # The only hard requirement: without the app there is nothing to say.
        app = await self.client.get_org_app(
            workspace_id=workspace_id,
            org_app_id=org_app_id,
            access_token=access_token,
        )

        (
            workspace_name,
            definition,
            listed_audiences,
            item_names,
            app_users,
            workspace_members,
        ) = await asyncio.gather(
            self._workspace_name(workspace_id, access_token),
            self._definition(
                cache_key=("org-app", workspace_id, org_app_id),
                start=lambda: self.client.start_org_app_definition(
                    workspace_id=workspace_id,
                    org_app_id=org_app_id,
                    access_token=access_token,
                ),
                access_token=access_token,
                warnings=warnings,
                label="the org app",
            ),
            self._listed_audiences(workspace_id, access_token, warnings),
            self._item_names(workspace_id, access_token),
            self._item_access(
                workspace_id=workspace_id,
                item_id=org_app_id,
                item_type=None,
                access_token=access_token,
                admin=admin,
            ),
            self._workspace_members(workspace_id, access_token, warnings),
        )
        app_users, app_users_note = app_users
        if app_users is None and app_users_note:
            warn(warnings, "APP_USERS_UNAVAILABLE", app_users_note)

        app_content = (definition or {}).get(DEFINITION_PART)
        elements = _flatten_elements(
            app_content.get("elements") if isinstance(app_content, dict) else None
        )
        parent_keys = _parent_keys(app, definition, org_app_id)

        audience_results = await asyncio.gather(
            *(
                bounded(
                    lambda audience=audience: self._audience(
                        workspace_id=workspace_id,
                        audience=audience,
                        access_token=access_token,
                        warnings=warnings,
                    )
                )
                for audience in listed_audiences or []
            )
        )
        unattributed = sum(1 for result in audience_results if result is None)
        audiences = [
            _audience_model(result, elements, item_names)
            for result in audience_results
            if result is not None and result["parent_id"] in parent_keys
        ]
        if _logical_id(app, definition) is None:
            # parentAppId holds the app's logical ID. Without it, an audience
            # that did not match may still belong to this app, so it is
            # counted as unknown rather than silently treated as another's.
            unmatched = sum(
                1
                for result in audience_results
                if result is not None and result["parent_id"] not in parent_keys
            )
            if unmatched:
                unattributed += unmatched
                warn(
                    warnings,
                    "ORG_APP_LOGICAL_ID_UNKNOWN",
                    "The app's logical ID is on neither the app item nor a "
                    "readable definition, so audiences cannot be matched to it "
                    "reliably.",
                )

        if include_member_access and audiences:
            await asyncio.gather(
                *(
                    bounded(
                        lambda audience=audience: self._audience_members(
                            workspace_id=workspace_id,
                            audience=audience,
                            access_token=access_token,
                            admin=admin,
                        )
                    )
                    for audience in audiences
                )
            )
        if any(audience.members_status == "complete" for audience in audiences):
            warn(
                warnings,
                "ORG_APP_AUDIENCE_MEMBERS_INFERRED",
                "Audience members are the principals holding permissions on "
                "each audience item. Microsoft documents that audience access "
                "is managed that way, but not that this API returns it; "
                "confirm on your tenant before relying on it.",
            )

        objects = _objects(elements, item_names, audiences)
        object_access_status: CoverageStatus = "not_requested"
        if include_object_access:
            await asyncio.gather(
                *(
                    bounded(
                        lambda item=item: self._object_access(
                            workspace_id=workspace_id,
                            item=item,
                            access_token=access_token,
                            admin=admin,
                        )
                    )
                    for item in objects
                    if item.object_type != LINK_ELEMENT
                )
            )
            object_access_status = (
                _aggregate(
                    item.access_status
                    for item in objects
                    if item.object_type != LINK_ELEMENT
                )
                if definition is not None
                else "unavailable"
            )

        if unattributed:
            warn(
                warnings,
                "ORG_APP_AUDIENCE_UNATTRIBUTED",
                f"{unattributed} audience(s) in this workspace could not be "
                "matched to an app (unreadable definition or unknown logical "
                "ID), so it is unknown whether they belong to this one.",
            )
        shared_hidden = [
            audience.name
            for audience in audiences
            if audience.has_access_to_hidden_content
        ]
        if shared_hidden:
            warn(
                warnings,
                "ORG_APP_HIDDEN_CONTENT_SHARED",
                "Access to hidden content is on for "
                + ", ".join(f"'{name}'" for name in shared_hidden)
                + ": anyone in any audience of this app can open every item, "
                "including items hidden from their audience.",
            )
        if workspace_members:
            warn(
                warnings,
                "WORKSPACE_MEMBERS_SEE_ALL_AUDIENCES",
                "Workspace members see every audience's content regardless of "
                "audience membership.",
            )

        audiences_status: CoverageStatus = (
            "unavailable"
            if listed_audiences is None
            else ("partial" if unattributed else "complete")
        )

        return AppAccessResponse(
            app_type="org_app",
            app_id=org_app_id,
            name=text(app, "displayName"),
            description=text(app, "description"),
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            logical_id=_logical_id(app, definition),
            app_users=app_users or [],
            workspace_members=workspace_members or [],
            audiences=audiences,
            objects=objects,
            coverage=AppAccessCoverage(
                app_users="complete" if app_users is not None else "unavailable",
                workspace_members=(
                    "complete" if workspace_members is not None else "unavailable"
                ),
                audiences=audiences_status,
                audience_members=(
                    _aggregate(audience.members_status for audience in audiences)
                    if include_member_access
                    else "not_requested"
                ),
                audience_content=audiences_status,
                objects="complete" if definition is not None else "unavailable",
                object_access=object_access_status,
            ),
            warnings=warnings,
        )

    # -- Reads ------------------------------------------------------------

    async def _workspace_name(
        self,
        workspace_id: str,
        access_token: str,
    ) -> str | None:
        try:
            workspace = await self.client.get_workspace(
                workspace_id=workspace_id,
                access_token=access_token,
            )
        except AppException:
            return None
        return text(workspace, "displayName")

    async def _definition(
        self,
        *,
        cache_key: tuple[str, ...],
        start: Callable[[], Awaitable[httpx.Response]],
        access_token: str,
        warnings: list[AppAccessWarning],
        label: str,
    ) -> dict[str, Any] | None:
        try:
            return await self.definition_reader.read_json_parts(
                cache_key=cache_key,
                start=start,
                access_token=access_token,
            )
        except AppException as exc:
            warn(
                warnings,
                "ORG_APP_DEFINITION_UNAVAILABLE",
                f"The definition of {label} could not be read ({exc.message}). "
                "Reading a definition needs read and write permission on the "
                "item.",
            )
            return None

    async def _listed_audiences(
        self,
        workspace_id: str,
        access_token: str,
        warnings: list[AppAccessWarning],
    ) -> list[dict[str, Any]] | None:
        try:
            return await collect_pages(
                lambda token: self.client.list_org_app_audiences(
                    workspace_id=workspace_id,
                    access_token=access_token,
                    continuation_token=token,
                )
            )
        except AppException as exc:
            warn(warnings, "ORG_APP_AUDIENCES_UNAVAILABLE", exc.message)
            return None

    async def _item_names(
        self,
        workspace_id: str,
        access_token: str,
    ) -> dict[str, dict[str, Any]]:
        """Workspace items by ID, to name the items an app references."""
        try:
            items = await collect_pages(
                lambda token: self.client.list_items(
                    workspace_id=workspace_id,
                    access_token=access_token,
                    continuation_token=token,
                )
            )
        except AppException:
            return {}
        return {
            item_id.casefold(): item
            for item in items
            if (item_id := text(item, "id")) is not None
        }

    async def _workspace_members(
        self,
        workspace_id: str,
        access_token: str,
        warnings: list[AppAccessWarning],
    ) -> list[AppPrincipal] | None:
        try:
            assignments = await collect_pages(
                lambda token: self.client.list_workspace_role_assignments(
                    workspace_id=workspace_id,
                    access_token=access_token,
                    continuation_token=token,
                )
            )
        except AppException as exc:
            warn(
                warnings,
                "WORKSPACE_MEMBERS_UNAVAILABLE",
                f"{exc.message} Listing workspace roles needs the Member role or "
                "higher.",
            )
            return None
        return [
            fabric_principal(
                assignment.get("principal"),
                source="Fabric ListWorkspaceRoleAssignments",
                access_right=text(assignment, "role"),
            )
            for assignment in assignments
        ]

    async def _item_access(
        self,
        *,
        workspace_id: str,
        item_id: str,
        item_type: str | None,
        access_token: str,
        admin: AdminGate,
    ) -> tuple[list[AppPrincipal] | None, str | None]:
        """Principals on one item, or None plus why they could not be read."""
        try:
            payload = await admin.call(
                lambda: self.client.list_item_access_details_as_admin(
                    workspace_id=workspace_id,
                    item_id=item_id,
                    item_type=item_type,
                    access_token=access_token,
                )
            )
        except AdminUnavailable:
            # Already explained once by the gate's warning.
            return None, None
        except AppException as exc:
            return None, exc.message
        return fabric_access_details(payload, source=ACCESS_SOURCE), None

    async def _audience(
        self,
        *,
        workspace_id: str,
        audience: dict[str, Any],
        access_token: str,
        warnings: list[AppAccessWarning],
    ) -> dict[str, Any] | None:
        """An audience with its decoded definition, or None if unreadable."""
        audience_id = text(audience, "id")
        if audience_id is None:
            return None
        definition = await self._definition(
            cache_key=("org-app-audience", workspace_id, audience_id),
            start=lambda: self.client.start_org_app_audience_definition(
                workspace_id=workspace_id,
                audience_id=audience_id,
                access_token=access_token,
            ),
            access_token=access_token,
            warnings=warnings,
            label=f"audience '{text(audience, 'displayName') or audience_id}'",
        )
        if definition is None:
            return None
        content = definition.get(DEFINITION_PART)
        content = content if isinstance(content, dict) else {}
        return {
            "item": audience,
            "definition": content,
            "parent_id": (text(content, "parentAppId") or "").casefold(),
        }

    async def _audience_members(
        self,
        *,
        workspace_id: str,
        audience: AppAudience,
        access_token: str,
        admin: AdminGate,
    ) -> None:
        members, note = await self._item_access(
            workspace_id=workspace_id,
            item_id=audience.id or "",
            item_type=None,
            access_token=access_token,
            admin=admin,
        )
        if members is None:
            audience.members_status = "unavailable"
            audience.note = note or "Needs a Fabric admin API."
            return
        audience.members = members
        audience.members_status = "complete"

    async def _object_access(
        self,
        *,
        workspace_id: str,
        item: AppObject,
        access_token: str,
        admin: AdminGate,
    ) -> None:
        if not item.workspace_object_id:
            item.access_status = "unavailable"
            item.access_note = (
                "The app references this item by logical ID only, so its access "
                "cannot be looked up."
            )
            return
        access, note = await self._item_access(
            workspace_id=workspace_id,
            item_id=item.workspace_object_id,
            item_type=item.object_type,
            access_token=access_token,
            admin=admin,
        )
        if access is None:
            item.access_status = "unavailable"
            item.access_note = note or "Needs a Fabric admin API."
            return
        item.access = access
        item.access_status = "complete"


def _flatten_elements(raw: Any) -> dict[str, dict[str, Any]]:
    """Every element in the app's navigation tree, keyed by element ID."""
    elements: dict[str, dict[str, Any]] = {}
    pending = list(raw) if isinstance(raw, list) else []
    while pending:
        element = pending.pop(0)
        if not isinstance(element, dict):
            continue
        element_id = text(element, "elementId")
        if element_id:
            elements[element_id.casefold()] = element
        children = element.get("elements")
        if isinstance(children, list):
            pending.extend(children)
    return elements


def _logical_id(app: dict[str, Any], definition: dict[str, Any] | None) -> str | None:
    platform = (definition or {}).get(PLATFORM_PART)
    config = platform.get("config") if isinstance(platform, dict) else None
    return text(app, "logicalId") or (
        text(config, "logicalId") if isinstance(config, dict) else None
    )


def _parent_keys(
    app: dict[str, Any],
    definition: dict[str, Any] | None,
    org_app_id: str,
) -> set[str]:
    """What an audience's ``parentAppId`` may hold for this app.

    Microsoft specifies the parent's logical ID; the item ID is accepted too so
    a definition written with it still attributes correctly.
    """
    return {
        value.casefold()
        for value in (text(app, "logicalId"), _logical_id(app, definition), org_app_id)
        if value
    }


def _audience_model(
    result: dict[str, Any],
    elements: dict[str, dict[str, Any]],
    item_names: dict[str, dict[str, Any]],
) -> AppAudience:
    item = result["item"]
    definition = result["definition"]
    settings = definition.get("settings")
    settings = settings if isinstance(settings, dict) else {}

    content: list[AppAudienceContent] = []
    for reference in definition.get("elementReferences") or []:
        if not isinstance(reference, dict):
            continue
        element = elements.get((text(reference, "elementId") or "").casefold(), {})
        object_id = (
            text(reference, "itemId")
            or text(element, "itemId")
            or text(reference, "itemLogicalId")
            or text(element, "itemLogicalId")
        )
        content.append(
            AppAudienceContent(
                object_id=object_id,
                object_type=(
                    text(reference, "itemType")
                    or text(element, "itemType")
                    or text(element, "elementType")
                ),
                name=_element_name(element, object_id, item_names),
                visible=reference.get("isElementHidden") is not True,
            )
        )

    hidden_access = settings.get("hasAccessToHiddenContent")
    return AppAudience(
        id=text(item, "id"),
        name=text(item, "displayName") or text(item, "id") or "?",
        description=text(item, "description"),
        source="org_app_audience",
        members_status="not_requested",
        content=content,
        content_status="complete",
        has_access_to_hidden_content=(
            hidden_access if isinstance(hidden_access, bool) else None
        ),
    )


def _objects(
    elements: dict[str, dict[str, Any]],
    item_names: dict[str, dict[str, Any]],
    audiences: list[AppAudience],
) -> list[AppObject]:
    visible_to: dict[str, list[str]] = {}
    for audience in audiences:
        for entry in audience.content:
            if entry.visible and entry.object_id:
                visible_to.setdefault(entry.object_id.casefold(), []).append(
                    audience.name
                )

    objects: list[AppObject] = []
    for element in elements.values():
        element_type = (text(element, "elementType") or "").casefold()
        if element_type == LINK_ELEMENT:
            objects.append(
                AppObject(
                    name=text(element, "displayName"),
                    object_type=LINK_ELEMENT,
                    web_url=text(element, "url"),
                    hidden_in_navigation=_hidden(element),
                    access_status="not_supported",
                    access_note="An external link; it has no Fabric access list.",
                )
            )
            continue
        if element_type != ITEM_ELEMENT:
            continue

        item_id = text(element, "itemId")
        object_id = item_id or text(element, "itemLogicalId")
        objects.append(
            AppObject(
                object_id=object_id,
                workspace_object_id=item_id,
                name=_element_name(element, object_id, item_names),
                object_type=(
                    text(element, "itemType")
                    or text(item_names.get((item_id or "").casefold()), "type")
                    or ITEM_ELEMENT
                ),
                hidden_in_navigation=_hidden(element),
                audiences=visible_to.get((object_id or "").casefold(), []),
                access_status="not_requested",
            )
        )
    return objects


def _element_name(
    element: dict[str, Any],
    object_id: str | None,
    item_names: dict[str, dict[str, Any]],
) -> str | None:
    return text(element, "displayName") or text(
        item_names.get((object_id or "").casefold()),
        "displayName",
    )


def _hidden(element: dict[str, Any]) -> bool | None:
    value = element.get("isHidden")
    return value if isinstance(value, bool) else None


def _aggregate(statuses: Any) -> CoverageStatus:
    values = set(statuses)
    if not values or values == {"complete"}:
        return "complete"
    if "complete" in values:
        return "partial"
    return "unavailable"
