from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.credentials import (
    get_fabric_access_token,
    get_powerbi_access_token,
)
from app.api.dependencies.security import require_lineage_api_key
from app.schemas.app_access import AppAccessResponse
from app.schemas.error import ErrorResponse
from app.services.org_app_access_service import OrgAppAccessService
from app.services.workspace_app_access_service import (
    MAX_AUDIENCE_HISTORY_DAYS,
    WorkspaceAppAccessService,
)

# The response lists people and their access, so both routers honour the
# admin key the same way the scanner routes do.
router = APIRouter(dependencies=[Depends(require_lineage_api_key)])
org_app_router = APIRouter(dependencies=[Depends(require_lineage_api_key)])

_ERROR_RESPONSES = {
    status_code: {"model": ErrorResponse, "description": description}
    for status_code, description in (
        (401, "No signed-in session, or a missing admin key."),
        (403, "The admin key is invalid, or the app cannot be read."),
        (404, "The app was not found."),
        (429, "The provider is rate limiting the caller."),
        (502, "The provider returned an unexpected response."),
    )
}


@router.get(
    "/{app_id}",
    response_model=AppAccessResponse,
    summary="Workspace app: metadata, audiences, objects and access",
    responses=_ERROR_RESPONSES,
)
async def get_workspace_app_access(
    app_id: UUID,
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
    audience_history_days: Annotated[
        int,
        Query(
            ge=0,
            le=MAX_AUDIENCE_HISTORY_DAYS,
            description=(
                "Rebuild audiences from this many days of CreateApp/UpdateApp "
                "activity events (0 = off). Power BI exposes workspace-app "
                "audiences nowhere else. Costs one admin call per day per "
                "activity type, against a 200-calls/hour quota."
            ),
        ),
    ] = 0,
    include_object_access: Annotated[
        bool,
        Query(description="Look up who can open each report and dashboard."),
    ] = True,
) -> AppAccessResponse:
    """A Power BI workspace app: the app, its content, who can reach it and
    at what access right, and the workspace members who see every audience.

    Admin sections need a Fabric administrator or a service principal allowed
    to call read-only admin APIs; without that they are marked `unavailable`
    in `coverage` rather than failing the request. Audience content is never
    available for workspace apps -- no API exposes it.
    """
    return await WorkspaceAppAccessService().build(
        app_id=str(app_id),
        access_token=powerbi_access_token,
        audience_history_days=audience_history_days,
        include_object_access=include_object_access,
    )


@org_app_router.get(
    "/{workspace_id}/org-apps/{org_app_id}",
    response_model=AppAccessResponse,
    summary="Org app: metadata, audiences, objects and access",
    responses=_ERROR_RESPONSES,
)
async def get_org_app_access(
    workspace_id: UUID,
    org_app_id: UUID,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    include_member_access: Annotated[
        bool,
        Query(description="Look up the members of each audience (admin, preview)."),
    ] = True,
    include_object_access: Annotated[
        bool,
        Query(description="Look up who can open each item (admin, preview)."),
    ] = True,
) -> AppAccessResponse:
    """A Fabric org app: the app, each audience with the items it shows or
    hides and its members, every item with its access list, and workspace
    roles.

    Definitions need read and write permission on the items; member and item
    access come from Fabric admin APIs (preview). Anything unreadable is
    marked in `coverage` and explained in `warnings`.
    """
    return await OrgAppAccessService().build(
        workspace_id=str(workspace_id),
        org_app_id=str(org_app_id),
        access_token=fabric_access_token,
        include_member_access=include_member_access,
        include_object_access=include_object_access,
    )
