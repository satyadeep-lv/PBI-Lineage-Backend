from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AppType = Literal["workspace_app", "org_app"]

# How complete one section of the response is. Power BI does not expose every
# part of an app through a public non-Scanner API, so each section says what
# it could and could not establish instead of leaving an empty list ambiguous.
CoverageStatus = Literal[
    # Everything the API can say was retrieved.
    "complete",
    # Some of it was retrieved, or the source is known to be incomplete.
    "partial",
    # The call that would answer it failed or was refused.
    "unavailable",
    # Skipped because the request did not ask for it.
    "not_requested",
    # No documented non-Scanner API returns it for this app type.
    "not_supported",
]


class AppPrincipal(BaseModel):
    """A user, group or service principal with some access."""

    id: str | None = None
    display_name: str | None = None
    email: str | None = None
    # User, Group, App (a service principal in Power BI's vocabulary),
    # ServicePrincipal, EntireTenant, EntireOrganization, ...
    principal_type: str | None = None
    # Power BI access-right value, e.g. ReadReshare, or a workspace role.
    access_right: str | None = None
    # Fabric item permissions (Read, Reshare, Explore, ...) plus any
    # additional permissions, or permissions named in an activity event.
    permissions: list[str] = Field(default_factory=list)
    source: str


class AppAudienceContent(BaseModel):
    object_id: str | None = None
    object_type: str | None = None
    name: str | None = None
    # Whether the item is shown to this audience. With "access to hidden
    # content" on, hidden items can still be opened.
    visible: bool


class AppAudience(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    source: Literal["org_app_audience", "activity_log"]
    members: list[AppPrincipal] = Field(default_factory=list)
    members_status: CoverageStatus
    # Audience-level permissions, as recorded in the activity log.
    permissions: list[str] = Field(default_factory=list)
    content: list[AppAudienceContent] = Field(default_factory=list)
    content_status: CoverageStatus
    has_access_to_hidden_content: bool | None = None
    # When the activity log last recorded a change to this audience.
    last_changed_at: datetime | None = None
    note: str | None = None


class AppObject(BaseModel):
    """A report, dashboard or other item the app publishes."""

    # The ID of the item as the app exposes it: for a workspace app, the app
    # copy, which differs from the workspace item.
    object_id: str | None = None
    workspace_object_id: str | None = None
    name: str | None = None
    object_type: str
    web_url: str | None = None
    hidden_in_navigation: bool | None = None
    # Names of the audiences the item is shown to (org apps only).
    audiences: list[str] = Field(default_factory=list)
    access: list[AppPrincipal] = Field(default_factory=list)
    access_status: CoverageStatus
    access_note: str | None = None


class AppAccessCoverage(BaseModel):
    app_users: CoverageStatus
    workspace_members: CoverageStatus
    audiences: CoverageStatus
    audience_members: CoverageStatus
    audience_content: CoverageStatus
    objects: CoverageStatus
    object_access: CoverageStatus


class AppAccessWarning(BaseModel):
    code: str
    message: str


class AppAccessResponse(BaseModel):
    app_type: AppType
    app_id: str
    name: str | None = None
    description: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    published_by: str | None = None
    last_updated: datetime | None = None
    # Org apps only: what an audience definition's parentAppId refers to.
    logical_id: str | None = None
    # Everyone with access to the app, as one flat list.
    app_users: list[AppPrincipal] = Field(default_factory=list)
    # Workspace roles. Workspace users see every audience's content, and a
    # workspace app does not repeat them in its own access list.
    workspace_members: list[AppPrincipal] = Field(default_factory=list)
    audiences: list[AppAudience] = Field(default_factory=list)
    objects: list[AppObject] = Field(default_factory=list)
    coverage: AppAccessCoverage
    warnings: list[AppAccessWarning] = Field(default_factory=list)
