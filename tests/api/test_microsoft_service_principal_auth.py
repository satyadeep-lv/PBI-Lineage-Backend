from app.core.auth_session import AUTH_SESSION_COOKIE
from app.schemas.auth import (
    MicrosoftApplicationTokenResult,
    MicrosoftServicePrincipalAuthResponse,
)
from app.services.auth.microsoft_service_principal_auth_service import (
    MicrosoftServicePrincipalAuthService,
)


def _response() -> MicrosoftServicePrincipalAuthResponse:
    return MicrosoftServicePrincipalAuthResponse(
        session_id="service-principal-session",
        status="authenticated",
        powerbi=MicrosoftApplicationTokenResult(
            token_acquired=True,
            resource="https://analysis.windows.net/powerbi/api",
            requested_scope=("https://analysis.windows.net/powerbi/api/.default"),
            message="Power BI application token acquired.",
        ),
        fabric=MicrosoftApplicationTokenResult(
            token_acquired=True,
            resource="https://api.fabric.microsoft.com",
            requested_scope=("https://api.fabric.microsoft.com/.default"),
            message="Fabric application token acquired.",
        ),
    )


def test_service_principal_authentication_sets_cookie_and_redacts_secret(
    client,
    monkeypatch,
):
    async def fake_authenticate(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ) -> MicrosoftServicePrincipalAuthResponse:
        assert tenant_id == "tenant-id"
        assert client_id == "client-id"
        assert client_secret == "secret-value"
        return _response()

    monkeypatch.setattr(
        MicrosoftServicePrincipalAuthService,
        "authenticate",
        fake_authenticate,
    )
    client.cookies.clear()

    response = client.post(
        "/api/v1/auth/microsoft/service-principal/session",
        json={
            "tenant_id": "tenant-id",
            "client_id": "client-id",
            "client_secret": "secret-value",
        },
    )

    assert response.status_code == 200
    assert response.cookies.get(AUTH_SESSION_COOKIE) == ("service-principal-session")
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "secret-value" not in response.text
    client.cookies.clear()


def test_service_principal_status_uses_session_cookie(
    client,
    monkeypatch,
):
    def fake_status(self, session_id):
        assert session_id == "service-principal-session"
        return _response()

    monkeypatch.setattr(
        MicrosoftServicePrincipalAuthService,
        "status",
        fake_status,
    )
    client.cookies.set(
        AUTH_SESSION_COOKIE,
        "service-principal-session",
    )

    response = client.get("/api/v1/auth/microsoft/service-principal/session/status")

    assert response.status_code == 200
    assert response.json()["authentication_method"] == "client_secret"
    client.cookies.clear()
