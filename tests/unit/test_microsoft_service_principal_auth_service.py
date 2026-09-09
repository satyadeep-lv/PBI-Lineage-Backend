import pytest

import app.services.auth.microsoft_service_principal_auth_service as service_module
from app.core.exceptions import ProviderAuthenticationFailedError
from app.core.microsoft_auth import (
    FABRIC_APPLICATION_SCOPE,
    POWERBI_APPLICATION_SCOPE,
)
from app.services.auth.device_auth_store import (
    delete_device_session,
    get_device_session,
)
from app.services.auth.microsoft_service_principal_auth_service import (
    MicrosoftServicePrincipalAuthService,
)


@pytest.mark.asyncio
async def test_authenticate_acquires_both_application_tokens_without_storing_secret(
    monkeypatch,
):
    calls: list[dict[str, object]] = []

    class FakeApplication:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def acquire_token_for_client(self, *, scopes):
            token = (
                "powerbi-token"
                if scopes == [POWERBI_APPLICATION_SCOPE]
                else "fabric-token"
            )
            return {
                "access_token": token,
                "expires_in": 3600,
            }

    monkeypatch.setattr(
        service_module.msal,
        "ConfidentialClientApplication",
        FakeApplication,
    )

    result = await MicrosoftServicePrincipalAuthService().authenticate(
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="secret-value",
    )

    try:
        session = get_device_session(result.session_id)

        assert result.status == "authenticated"
        assert result.powerbi.token_acquired is True
        assert result.fabric.token_acquired is True
        assert session is not None
        assert session.authentication_method == "client_secret"
        assert session.powerbi_access_token == "powerbi-token"
        assert session.fabric_access_token == "fabric-token"
        assert not hasattr(session, "client_secret")
        assert {call["client_credential"] for call in calls} == {"secret-value"}
        assert {call["client_id"] for call in calls} == {"client-id"}
    finally:
        delete_device_session(result.session_id)


@pytest.mark.asyncio
async def test_authenticate_keeps_powerbi_session_when_fabric_token_fails(
    monkeypatch,
):
    class FakeApplication:
        def __init__(self, **kwargs):
            pass

        def acquire_token_for_client(self, *, scopes):
            if scopes == [POWERBI_APPLICATION_SCOPE]:
                return {
                    "access_token": "powerbi-token",
                    "expires_in": 3600,
                }
            assert scopes == [FABRIC_APPLICATION_SCOPE]
            return {"error": "unauthorized_client"}

    monkeypatch.setattr(
        service_module.msal,
        "ConfidentialClientApplication",
        FakeApplication,
    )

    result = await MicrosoftServicePrincipalAuthService().authenticate(
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="secret-value",
    )

    try:
        assert result.status == "partial"
        assert result.powerbi.token_acquired is True
        assert result.fabric.token_acquired is False
        assert result.fabric.error_code == "unauthorized_client"
    finally:
        delete_device_session(result.session_id)


@pytest.mark.asyncio
async def test_authenticate_rejects_failed_powerbi_token_request(
    monkeypatch,
):
    class FakeApplication:
        def __init__(self, **kwargs):
            pass

        def acquire_token_for_client(self, *, scopes):
            return {"error": "invalid_client"}

    monkeypatch.setattr(
        service_module.msal,
        "ConfidentialClientApplication",
        FakeApplication,
    )

    with pytest.raises(ProviderAuthenticationFailedError):
        await MicrosoftServicePrincipalAuthService().authenticate(
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="wrong-secret",
        )
