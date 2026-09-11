import base64
import hashlib

import pytest

import app.services.auth.microsoft_sso_auth_service as service_module
from app.clients.fabric_client import FabricClient
from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import (
    AuthenticationStateInvalidError,
    ProviderAuthenticationFailedError,
)
from app.core.microsoft_auth import generate_pkce_pair
from app.services.auth.device_auth_store import (
    delete_device_session,
    get_device_session,
)
from app.services.auth.microsoft_sso_auth_service import MicrosoftSsoAuthService


class _FakeApplication:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def get_authorization_request_url(
        self,
        *,
        scopes,
        state,
        redirect_uri,
        code_challenge,
        code_challenge_method,
    ):
        return (
            "https://login.microsoftonline.com/authorize"
            f"?state={state}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method={code_challenge_method}"
        )

    def acquire_token_by_authorization_code(
        self,
        code,
        *,
        scopes,
        redirect_uri,
        code_verifier,
    ):
        if code == "bad-code":
            return {"error": "invalid_grant"}

        return {
            "access_token": "powerbi-token",
            "expires_in": 3600,
            "scope": " ".join(scopes),
        }

    def get_accounts(self):
        return [{"username": "test-user"}]

    def acquire_token_silent_with_error(self, scopes, *, account):
        return {
            "access_token": "fabric-token",
            "expires_in": 3600,
        }


async def _fake_validate_connection(self, access_token):
    return True


def _extract_state(authorization_url: str) -> str:
    return authorization_url.split("state=")[1].split("&")[0]


def test_generate_pkce_pair_challenge_matches_verifier():
    verifier, challenge = generate_pkce_pair()

    assert 43 <= len(verifier) <= 128

    expected_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )

    assert challenge == expected_challenge


def test_build_authorization_url_includes_pkce_and_state(monkeypatch):
    monkeypatch.setattr(
        service_module.msal,
        "PublicClientApplication",
        _FakeApplication,
    )

    url = MicrosoftSsoAuthService().build_authorization_url(
        tenant_id="test-tenant",
        client_id="test-client",
        redirect_uri="https://api.example.com/callback",
        post_login_redirect_uri="https://app.example.com",
    )

    assert "state=" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url


@pytest.mark.asyncio
async def test_complete_login_creates_authenticated_sso_session(monkeypatch):
    monkeypatch.setattr(
        service_module.msal,
        "PublicClientApplication",
        _FakeApplication,
    )
    monkeypatch.setattr(
        PowerBIClient,
        "validate_connection",
        _fake_validate_connection,
    )
    monkeypatch.setattr(
        FabricClient,
        "validate_connection",
        _fake_validate_connection,
    )

    service = MicrosoftSsoAuthService()
    authorization_url = service.build_authorization_url(
        tenant_id="test-tenant",
        client_id="test-client",
        redirect_uri="https://api.example.com/callback",
        post_login_redirect_uri=None,
    )
    state = _extract_state(authorization_url)

    session_id, post_login_redirect_uri = await service.complete_login(
        code="good-code",
        state=state,
    )

    try:
        session = get_device_session(session_id)

        assert session is not None
        assert session.authentication_method == "sso"
        assert session.status == "authenticated"
        assert session.powerbi_access_token == "powerbi-token"
        assert session.fabric_access_token == "fabric-token"
        assert post_login_redirect_uri is None
    finally:
        delete_device_session(session_id)


@pytest.mark.asyncio
async def test_complete_login_rejects_unknown_state():
    with pytest.raises(AuthenticationStateInvalidError):
        await MicrosoftSsoAuthService().complete_login(
            code="any-code",
            state="unknown-state",
        )


@pytest.mark.asyncio
async def test_complete_login_rejects_failed_token_exchange(monkeypatch):
    monkeypatch.setattr(
        service_module.msal,
        "PublicClientApplication",
        _FakeApplication,
    )

    service = MicrosoftSsoAuthService()
    authorization_url = service.build_authorization_url(
        tenant_id="test-tenant",
        client_id="test-client",
        redirect_uri="https://api.example.com/callback",
        post_login_redirect_uri=None,
    )
    state = _extract_state(authorization_url)

    with pytest.raises(ProviderAuthenticationFailedError):
        await service.complete_login(
            code="bad-code",
            state=state,
        )
