import base64
import binascii
import json
from typing import Any

MICROSOFT_LOGIN_BASE_URL = "https://login.microsoftonline.com"

POWERBI_RESOURCE = "https://analysis.windows.net/powerbi/api"

FABRIC_RESOURCE = "https://api.fabric.microsoft.com"

POWERBI_APPLICATION_SCOPE = f"{POWERBI_RESOURCE}/.default"

FABRIC_APPLICATION_SCOPE = f"{FABRIC_RESOURCE}/.default"

POWERBI_SCOPES = [
    f"{POWERBI_RESOURCE}/Workspace.Read.All",
    f"{POWERBI_RESOURCE}/Report.Read.All",
    f"{POWERBI_RESOURCE}/Dataset.Read.All",
]

FABRIC_SCOPES = [
    f"{FABRIC_RESOURCE}/Workspace.Read.All",
    f"{FABRIC_RESOURCE}/Item.ReadWrite.All",
]

MICROSOFT_TEST_SCOPES = [
    ("https://analysis.windows.net/powerbi/api/Workspace.Read.All"),
]


def get_scope_permission(scope: str) -> str:
    normalized = scope.rstrip("/")

    if "/" not in normalized:
        return normalized

    return normalized.rsplit("/", 1)[-1]


def normalize_scope_permissions(
    scopes: list[str],
) -> list[str]:
    permissions: list[str] = []
    seen: set[str] = set()

    for scope in scopes:
        if not isinstance(scope, str):
            continue

        permission = get_scope_permission(scope)

        if not permission or permission in seen:
            continue

        seen.add(permission)
        permissions.append(permission)

    return permissions


def _decode_unverified_jwt_payload(
    access_token: str,
) -> dict[str, Any]:
    parts = access_token.split(".")

    if len(parts) < 2:
        return {}

    encoded_payload = parts[1]

    padded_payload = encoded_payload + "=" * ((4 - len(encoded_payload) % 4) % 4)

    try:
        decoded = base64.urlsafe_b64decode(padded_payload.encode("ascii"))

        payload = json.loads(decoded.decode("utf-8"))

    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ):
        return {}

    if not isinstance(payload, dict):
        return {}

    return payload


def extract_granted_scopes(
    token_result: dict[str, Any],
) -> list[str]:
    scope_values: list[str] = []

    raw_scope = token_result.get("scope")

    if isinstance(raw_scope, str):
        scope_values.extend(raw_scope.split())

    access_token = token_result.get("access_token")

    if isinstance(access_token, str):
        payload = _decode_unverified_jwt_payload(access_token)

        raw_scp = payload.get("scp")

        if isinstance(raw_scp, str):
            scope_values.extend(raw_scp.split())

        raw_roles = payload.get("roles")

        if isinstance(raw_roles, list):
            scope_values.extend(role for role in raw_roles if isinstance(role, str))

    return normalize_scope_permissions(scope_values)
