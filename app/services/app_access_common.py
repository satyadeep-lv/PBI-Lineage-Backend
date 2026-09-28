"""Pieces shared by the workspace-app and org-app access services."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from app.core.exceptions import (
    InsufficientPermissionsError,
    InvalidAccessTokenError,
    UpstreamRateLimitError,
)
from app.schemas.app_access import AppAccessWarning, AppPrincipal

T = TypeVar("T")

MAX_PAGES = 50

ADMIN_REQUIREMENT = (
    "Admin APIs need a Fabric administrator signed in with Tenant.Read.All, or "
    "a service principal allowed by the 'Service principals can access "
    "read-only admin APIs' tenant setting."
)


class AdminUnavailable(Exception):
    """An admin API was refused (or skipped after an earlier refusal)."""


class AdminGate:
    """Calls admin APIs until the first refusal, then stops trying.

    A session that is not an administrator is refused by every admin API, and
    they share a small hourly quota. Once one says no, the rest of the request
    skips them instead of spending that quota on answers it already knows.
    """

    def __init__(
        self,
        *,
        label: str,
        warnings: list[AppAccessWarning],
    ) -> None:
        self.label = label
        self.warnings = warnings
        self.is_open = True

    async def call(self, factory: Callable[[], Awaitable[T]]) -> T:
        if not self.is_open:
            raise AdminUnavailable()
        try:
            return await factory()
        except (InvalidAccessTokenError, InsufficientPermissionsError) as exc:
            self._close(
                "ADMIN_API_UNAVAILABLE",
                f"{self.label} admin APIs refused this session ({exc.message}); "
                "sections that need them are marked unavailable. " + ADMIN_REQUIREMENT,
            )
            raise AdminUnavailable() from exc
        except UpstreamRateLimitError as exc:
            self._close(
                "ADMIN_API_RATE_LIMITED",
                f"{self.label} admin APIs are rate limiting this tenant "
                f"(retry after {exc.retry_after or 'a while'}); the remaining "
                "admin-only sections were skipped.",
            )
            raise AdminUnavailable() from exc

    def _close(self, code: str, message: str) -> None:
        if self.is_open:
            self.is_open = False
            self.warnings.append(AppAccessWarning(code=code, message=message))


class Bounded:
    """Caps how many provider calls one request runs at once."""

    def __init__(self, limit: int) -> None:
        self._semaphore = asyncio.Semaphore(limit)

    async def __call__(self, factory: Callable[[], Awaitable[T]]) -> T:
        async with self._semaphore:
            return await factory()


def warn(warnings: list[AppAccessWarning], code: str, message: str) -> None:
    warnings.append(AppAccessWarning(code=code, message=message))


async def collect_pages(
    fetch: Callable[[str | None], Awaitable[dict[str, Any]]],
    *,
    items_key: str = "value",
) -> list[dict[str, Any]]:
    """Follow a Fabric ``continuationToken`` to the end of a listing."""
    items: list[dict[str, Any]] = []
    token: str | None = None
    for _ in range(MAX_PAGES):
        page = await fetch(token)
        values = page.get(items_key)
        if isinstance(values, list):
            items.extend(value for value in values if isinstance(value, dict))
        token = page.get("continuationToken")
        if not isinstance(token, str) or not token:
            break
    return items


def powerbi_principal(
    raw: dict[str, Any],
    *,
    access_right_key: str,
    source: str,
) -> AppPrincipal:
    """A principal from a Power BI admin ``*Users`` response."""
    principal_type = text(raw, "principalType")
    if principal_type == "None":
        # Power BI's PrincipalType "None" means organization-wide access.
        principal_type = "EntireOrganization"
    return AppPrincipal(
        id=text(raw, "graphId") or text(raw, "identifier"),
        display_name=text(raw, "displayName"),
        email=text(raw, "emailAddress"),
        principal_type=principal_type,
        access_right=text(raw, access_right_key),
        source=source,
    )


def fabric_principal(
    raw_principal: Any,
    *,
    source: str,
    access_right: str | None = None,
    permissions: list[str] | None = None,
) -> AppPrincipal:
    """A principal from a Fabric ``Principal`` object."""
    principal = raw_principal if isinstance(raw_principal, dict) else {}
    user_details = principal.get("userDetails")
    email = (
        text(user_details, "userPrincipalName")
        if isinstance(user_details, dict)
        else None
    )
    return AppPrincipal(
        id=text(principal, "id"),
        display_name=text(principal, "displayName"),
        email=email,
        principal_type=text(principal, "type"),
        access_right=access_right,
        permissions=permissions or [],
        source=source,
    )


def fabric_access_details(
    payload: dict[str, Any],
    *,
    source: str,
) -> list[AppPrincipal]:
    """Principals from a Fabric admin ``ItemAccessDetailsResponse``."""
    principals: list[AppPrincipal] = []
    for entry in payload.get("accessDetails") or []:
        if not isinstance(entry, dict):
            continue
        details = entry.get("itemAccessDetails")
        details = details if isinstance(details, dict) else {}
        permissions = [
            str(value)
            for key in ("permissions", "additionalPermissions")
            for value in (details.get(key) or [])
            if isinstance(value, str)
        ]
        principals.append(
            fabric_principal(
                entry.get("principal"),
                source=source,
                permissions=list(dict.fromkeys(permissions)),
            )
        )
    return principals


def text(payload: Any, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
