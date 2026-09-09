from uuid import uuid4

from app.core.auth_session import AUTH_SESSION_COOKIE
from app.core.microsoft_auth import (
    FABRIC_SCOPES,
    POWERBI_SCOPES,
    get_scope_permission,
)
from app.services.auth.device_auth_store import (
    DeviceAuthSession,
    delete_device_session,
    save_device_session,
)
from app.services.auth.microsoft_device_auth_service import (
    MicrosoftDeviceAuthService,
)


def _scope_permissions(
    scopes: list[str],
) -> list[str]:
    return [get_scope_permission(scope) for scope in scopes]


def _create_session(
    *,
    status: str,
    powerbi_connected: bool | None = None,
    fabric_connected: bool | None = None,
    error_message: str | None = None,
    powerbi_error_code: str | None = None,
    fabric_error_code: str | None = None,
    powerbi_granted_scopes: list[str] | None = None,
    fabric_granted_scopes: list[str] | None = None,
) -> str:
    session_id = str(uuid4())

    session = DeviceAuthSession(
        flow={},
        tenant_id="test-tenant",
        client_id="test-client",
    )

    session.status = status
    session.powerbi_connected = powerbi_connected
    session.fabric_connected = fabric_connected
    session.error_message = error_message
    session.powerbi_error_code = powerbi_error_code
    session.fabric_error_code = fabric_error_code
    session.powerbi_granted_scopes = list(powerbi_granted_scopes or [])
    session.fabric_granted_scopes = list(fabric_granted_scopes or [])

    save_device_session(
        session_id,
        session,
    )

    return session_id


def test_microsoft_device_start_success(
    client,
    monkeypatch,
):
    async def fake_start(
        self,
        *,
        tenant_id: str,
        client_id: str,
    ):
        return (
            "test-session-id",
            {
                "verification_uri": ("https://microsoft.com/devicelogin"),
                "user_code": "TEST-CODE",
                "message": "Authenticate with Microsoft.",
                "expires_in": 900,
            },
        )

    monkeypatch.setattr(
        MicrosoftDeviceAuthService,
        "start",
        fake_start,
    )

    client.cookies.clear()

    response = client.post(
        "/api/v1/auth/microsoft/device/start",
        json={
            "tenant_id": "test-tenant",
            "client_id": "test-client",
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["session_id"] == "test-session-id"
    assert payload["user_code"] == "TEST-CODE"
    assert payload["expires_in"] == 900

    assert response.cookies.get(AUTH_SESSION_COOKIE) == "test-session-id"

    client.cookies.clear()


def test_device_status_requires_session(
    client,
):
    client.cookies.clear()

    response = client.get("/api/v1/auth/microsoft/device/status")

    assert response.status_code == 401


def test_device_status_pending(
    client,
):
    session_id = _create_session(
        status="pending",
    )

    try:
        client.cookies.clear()

        client.cookies.set(
            AUTH_SESSION_COOKIE,
            session_id,
        )

        response = client.get("/api/v1/auth/microsoft/device/status")

        assert response.status_code == 200

        payload = response.json()

        assert payload["status"] == "pending"

    finally:
        delete_device_session(session_id)
        client.cookies.clear()


def test_device_status_authenticated(
    client,
):
    session_id = _create_session(
        status="authenticated",
        powerbi_connected=True,
        fabric_connected=True,
        powerbi_granted_scopes=(_scope_permissions(POWERBI_SCOPES)),
        fabric_granted_scopes=(_scope_permissions(FABRIC_SCOPES)),
    )

    try:
        client.cookies.clear()

        client.cookies.set(
            AUTH_SESSION_COOKIE,
            session_id,
        )

        response = client.get("/api/v1/auth/microsoft/device/status")

        assert response.status_code == 200

        payload = response.json()

        assert payload["status"] == "authenticated"

        assert payload["powerbi"]["connected"] is True

        assert payload["fabric"]["connected"] is True

        assert payload["powerbi"]["requested_scopes"] == POWERBI_SCOPES
        assert payload["powerbi"]["missing_scopes"] == []
        assert payload["fabric"]["requested_scopes"] == FABRIC_SCOPES
        assert payload["fabric"]["missing_scopes"] == []

    finally:
        delete_device_session(session_id)
        client.cookies.clear()


def test_device_status_by_session_id_includes_scope_details(
    client,
):
    session_id = _create_session(
        status="authenticated",
        powerbi_connected=True,
        fabric_connected=False,
        powerbi_granted_scopes=(_scope_permissions(POWERBI_SCOPES)),
        fabric_error_code="interaction_required",
    )

    try:
        response = client.get(f"/api/v1/auth/microsoft/device/{session_id}/status")

        assert response.status_code == 200

        payload = response.json()

        assert payload["status"] == "authenticated"
        assert payload["powerbi"]["missing_scopes"] == []
        assert payload["fabric"]["connected"] is False
        assert payload["fabric"]["error_code"] == "interaction_required"
        assert payload["fabric"]["missing_scopes"]

    finally:
        delete_device_session(session_id)
        client.cookies.clear()


def test_device_status_powerbi_connected_fabric_not_connected(
    client,
):
    session_id = _create_session(
        status="authenticated",
        powerbi_connected=True,
        fabric_connected=False,
        powerbi_granted_scopes=(_scope_permissions(POWERBI_SCOPES)),
        fabric_granted_scopes=["Workspace.Read.All"],
        fabric_error_code="interaction_required",
    )

    try:
        client.cookies.clear()

        client.cookies.set(
            AUTH_SESSION_COOKIE,
            session_id,
        )

        response = client.get("/api/v1/auth/microsoft/device/status")

        assert response.status_code == 200

        payload = response.json()

        assert payload["status"] == "authenticated"

        assert payload["powerbi"]["connected"] is True

        assert payload["fabric"]["connected"] is False

        assert payload["fabric"]["error_code"] == "interaction_required"
        assert payload["fabric"]["granted_scopes"] == ["Workspace.Read.All"]
        assert (
            "https://api.fabric.microsoft.com/"
            "Item.ReadWrite.All" in payload["fabric"]["missing_scopes"]
        )

    finally:
        delete_device_session(session_id)
        client.cookies.clear()


def test_device_status_failed(
    client,
):
    session_id = _create_session(
        status="failed",
        powerbi_connected=False,
        fabric_connected=False,
        error_message="Authentication failed.",
    )

    try:
        client.cookies.clear()

        client.cookies.set(
            AUTH_SESSION_COOKIE,
            session_id,
        )

        response = client.get("/api/v1/auth/microsoft/device/status")

        assert response.status_code == 200

        payload = response.json()

        assert payload["status"] == "failed"

        assert payload["message"] == "Authentication failed."

    finally:
        delete_device_session(session_id)
        client.cookies.clear()


def test_logout_success(
    client,
):
    session_id = _create_session(
        status="authenticated",
        powerbi_connected=True,
        fabric_connected=True,
    )

    client.cookies.clear()

    client.cookies.set(
        AUTH_SESSION_COOKIE,
        session_id,
    )

    response = client.post("/api/v1/auth/microsoft/device/logout")

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "logged_out"

    client.cookies.clear()


def test_request_id_propagation(
    client,
):
    client.cookies.clear()

    request_id = "auth-test-request-id"

    response = client.get(
        "/api/v1/auth/microsoft/device/status",
        headers={
            "X-Request-ID": request_id,
        },
    )

    assert response.status_code == 401

    assert response.headers["X-Request-ID"] == request_id
