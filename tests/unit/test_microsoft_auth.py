import base64
import json

from app.core.microsoft_auth import (
    extract_granted_scopes,
    get_scope_permission,
    normalize_scope_permissions,
)


def _encode_segment(
    payload: dict[str, object],
) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )


def _token(
    payload: dict[str, object],
) -> str:
    return f"{_encode_segment({'alg': 'none'})}.{_encode_segment(payload)}.signature"


def test_get_scope_permission_from_resource_scope():
    assert (
        get_scope_permission("https://api.fabric.microsoft.com/Item.ReadWrite.All")
        == "Item.ReadWrite.All"
    )


def test_normalize_scope_permissions_deduplicates():
    assert normalize_scope_permissions(
        [
            "https://api.fabric.microsoft.com/Workspace.Read.All",
            "Workspace.Read.All",
            "Item.ReadWrite.All",
        ]
    ) == [
        "Workspace.Read.All",
        "Item.ReadWrite.All",
    ]


def test_extract_granted_scopes_from_result_scope():
    result = {"scope": ("Workspace.Read.All Item.ReadWrite.All")}

    assert extract_granted_scopes(result) == [
        "Workspace.Read.All",
        "Item.ReadWrite.All",
    ]


def test_extract_granted_scopes_from_jwt_scp():
    result = {
        "access_token": _token({"scp": ("Workspace.Read.All Item.ReadWrite.All")})
    }

    assert extract_granted_scopes(result) == [
        "Workspace.Read.All",
        "Item.ReadWrite.All",
    ]
