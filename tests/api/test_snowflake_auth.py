from app.schemas.snowflake_auth import (
    SnowflakeAuthenticationResponse,
    SnowflakeAuthenticationStatusResponse,
)
from app.schemas.snowflake_lineage import (
    SnowflakeDeepLineageResponse,
    SnowflakeLineageSnapshot,
)
from app.services.auth.snowflake_session_auth_service import (
    SnowflakeSessionAuthService,
)
from app.services.auth.snowflake_session_store import SNOWFLAKE_SESSION_COOKIE
from app.services.snowflake_deep_lineage_service import (
    SnowflakeDeepLineageService,
)


def _auth_response() -> SnowflakeAuthenticationResponse:
    return SnowflakeAuthenticationResponse(
        session_id="snowflake-session-id",
        authentication_method="password",
        account_identifier="organization-account",
        user="lineage_user",
        current_role="LINEAGE_READER",
        expires_in=2700,
    )


def test_snowflake_authentication_sets_http_only_session_cookie(client, monkeypatch):
    closed: list[str] = []
    monkeypatch.setattr(
        SnowflakeSessionAuthService,
        "authenticate",
        lambda self, request: _auth_response(),
    )
    monkeypatch.setattr(
        SnowflakeSessionAuthService,
        "logout",
        lambda self, session_id: closed.append(session_id),
    )
    client.cookies.set(SNOWFLAKE_SESSION_COOKIE, "previous-session-id")

    response = client.post(
        "/api/v1/auth/snowflake/session",
        json={
            "authentication_method": "password",
            "account_identifier": "organization-account",
            "user": "lineage_user",
            "password": "secret-password",
        },
    )

    assert response.status_code == 200
    assert response.cookies.get(SNOWFLAKE_SESSION_COOKIE) == "snowflake-session-id"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "secret-password" not in response.text
    assert closed == ["previous-session-id"]
    client.cookies.clear()


def test_snowflake_status_and_logout_use_session_cookie(client, monkeypatch):
    closed: list[str] = []
    monkeypatch.setattr(
        SnowflakeSessionAuthService,
        "status",
        lambda self, session_id: SnowflakeAuthenticationStatusResponse(
            authentication_method="oauth",
            account_identifier="organization-account",
            user="lineage_user",
            expires_in=1200,
        ),
    )
    monkeypatch.setattr(
        SnowflakeSessionAuthService,
        "logout",
        lambda self, session_id: closed.append(session_id),
    )
    client.cookies.set(SNOWFLAKE_SESSION_COOKIE, "snowflake-session-id")

    status = client.get("/api/v1/auth/snowflake/session/status")
    logout = client.delete("/api/v1/auth/snowflake/session")

    assert status.status_code == 200
    assert status.json()["status"] == "authenticated"
    assert logout.status_code == 200
    assert closed == ["snowflake-session-id"]
    client.cookies.clear()


def test_snowflake_trace_requires_session_cookie(client):
    client.cookies.clear()

    response = client.post(
        "/api/v1/lineage/snowflake/trace",
        json={"object_name": "DB.SCHEMA.TABLE"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["provider"] == "snowflake"


def test_snowflake_trace_uses_authenticated_session(client, monkeypatch):
    captured: dict[str, str] = {}

    def fake_trace(self, session_id, request):
        captured["session_id"] = session_id
        captured["object_name"] = request.object_name
        return SnowflakeDeepLineageResponse(
            account_identifier="organization-account",
            starting_object_name=request.object_name,
            object_domain="TABLE",
            direction="UPSTREAM",
            max_depth=50,
            snapshot=SnowflakeLineageSnapshot(
                account_identifier="organization-account"
            ),
        )

    monkeypatch.setattr(
        SnowflakeDeepLineageService,
        "trace_session",
        fake_trace,
    )
    client.cookies.set(SNOWFLAKE_SESSION_COOKIE, "snowflake-session-id")

    response = client.post(
        "/api/v1/lineage/snowflake/trace",
        json={"object_name": "DB.SCHEMA.TABLE"},
    )

    assert response.status_code == 200
    assert captured == {
        "session_id": "snowflake-session-id",
        "object_name": "DB.SCHEMA.TABLE",
    }
    client.cookies.clear()
