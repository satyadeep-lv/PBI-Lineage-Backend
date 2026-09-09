import pytest

import app.services.auth.microsoft_device_auth_service as service_module
from app.core.exceptions import InsufficientPermissionsError
from app.core.microsoft_auth import FABRIC_SCOPES
from app.services.auth.device_auth_store import (
    DeviceAuthSession,
    delete_device_session,
    get_device_session,
    save_device_session,
)
from app.services.auth.microsoft_device_auth_service import (
    MicrosoftDeviceAuthService,
)


class FakeMsalApp:
    def __init__(
        self,
        *,
        device_result=None,
        accounts=None,
        silent_result=None,
    ):
        self.device_result = device_result or {}
        self.accounts = accounts or []
        self.silent_result = silent_result
        self.silent_scopes = None
        self.silent_account = None

    def acquire_token_by_device_flow(self, flow):
        return self.device_result

    def get_accounts(self):
        return self.accounts

    def acquire_token_silent_with_error(
        self,
        scopes,
        *,
        account,
    ):
        self.silent_scopes = scopes
        self.silent_account = account
        return self.silent_result


class PassingPowerBIClient:
    async def validate_connection(self, access_token):
        return True


class FailingPowerBIClient:
    async def validate_connection(self, access_token):
        raise InsufficientPermissionsError("powerbi")


class PassingFabricClient:
    async def validate_connection(self, access_token):
        return True


class FailingFabricClient:
    async def validate_connection(self, access_token):
        raise InsufficientPermissionsError("fabric")


@pytest.mark.asyncio
async def test_wait_for_authentication_sets_failed_when_powerbi_validation_fails(
    monkeypatch,
):
    app = FakeMsalApp(
        device_result={
            "access_token": "powerbi-token",
            "expires_in": 3600,
            "scope": "Workspace.Read.All",
        }
    )

    monkeypatch.setattr(
        service_module.msal,
        "PublicClientApplication",
        lambda **kwargs: app,
    )
    monkeypatch.setattr(
        service_module,
        "PowerBIClient",
        lambda: FailingPowerBIClient(),
    )

    session_id = "powerbi-validation-failed"
    save_device_session(
        session_id,
        DeviceAuthSession(
            tenant_id="tenant",
            client_id="client",
            flow={"device_code": "device-code"},
        ),
    )

    try:
        service = MicrosoftDeviceAuthService()

        await service._wait_for_authentication(
            session_id=session_id,
        )

        session = get_device_session(session_id)

        assert session is not None
        assert session.status == "failed"
        assert session.powerbi_access_token is None
        assert session.powerbi_connected is False
        assert session.powerbi_error_code == "AUTH_INSUFFICIENT_PERMISSIONS"
        assert session.fabric_connected is None

    finally:
        delete_device_session(session_id)


@pytest.mark.asyncio
async def test_wait_for_authentication_keeps_powerbi_when_fabric_account_not_cached(
    monkeypatch,
):
    app = FakeMsalApp(
        device_result={
            "access_token": "powerbi-token",
            "expires_in": 3600,
            "scope": ("Workspace.Read.All Report.Read.All Dataset.Read.All"),
        },
        accounts=[],
    )

    monkeypatch.setattr(
        service_module.msal,
        "PublicClientApplication",
        lambda **kwargs: app,
    )
    monkeypatch.setattr(
        service_module,
        "PowerBIClient",
        lambda: PassingPowerBIClient(),
    )

    session_id = "powerbi-ok-fabric-no-account"
    save_device_session(
        session_id,
        DeviceAuthSession(
            tenant_id="tenant",
            client_id="client",
            flow={"device_code": "device-code"},
        ),
    )

    try:
        service = MicrosoftDeviceAuthService()

        await service._wait_for_authentication(
            session_id=session_id,
        )

        session = get_device_session(session_id)

        assert session is not None
        assert session.status == "authenticated"
        assert session.powerbi_access_token == "powerbi-token"
        assert session.powerbi_connected is True
        assert session.powerbi_error_code is None
        assert session.fabric_access_token is None
        assert session.fabric_connected is False
        assert session.fabric_error_code == "account_not_cached"
        assert session.fabric_granted_scopes == []

    finally:
        delete_device_session(session_id)


@pytest.mark.asyncio
async def test_try_acquire_fabric_token_stores_token_and_granted_scopes(
    monkeypatch,
):
    app = FakeMsalApp(
        accounts=[{"home_account_id": "account-1"}],
        silent_result={
            "access_token": "fabric-token",
            "expires_in": 3600,
            "scope": ("Workspace.Read.All Item.ReadWrite.All"),
        },
    )

    monkeypatch.setattr(
        service_module,
        "FabricClient",
        lambda: PassingFabricClient(),
    )

    session = DeviceAuthSession(
        tenant_id="tenant",
        client_id="client",
    )

    service = MicrosoftDeviceAuthService()

    await service._try_acquire_fabric_token(
        app=app,
        session=session,
    )

    assert app.silent_scopes == FABRIC_SCOPES
    assert session.fabric_access_token == "fabric-token"
    assert session.fabric_connected is True
    assert session.fabric_error_code is None
    assert session.fabric_granted_scopes == [
        "Workspace.Read.All",
        "Item.ReadWrite.All",
    ]
    assert session.fabric_token_expires_at is not None


@pytest.mark.asyncio
async def test_try_acquire_fabric_token_sets_interaction_required_without_token():
    app = FakeMsalApp(
        accounts=[{"home_account_id": "account-1"}],
        silent_result=None,
    )

    session = DeviceAuthSession(
        tenant_id="tenant",
        client_id="client",
    )
    session.fabric_granted_scopes = ["Workspace.Read.All"]

    service = MicrosoftDeviceAuthService()

    await service._try_acquire_fabric_token(
        app=app,
        session=session,
    )

    assert session.fabric_access_token is None
    assert session.fabric_connected is False
    assert session.fabric_error_code == "interaction_required"
    assert session.fabric_granted_scopes == []


@pytest.mark.asyncio
async def test_try_acquire_fabric_token_preserves_validation_error_code(
    monkeypatch,
):
    app = FakeMsalApp(
        accounts=[{"home_account_id": "account-1"}],
        silent_result={
            "access_token": "fabric-token",
            "expires_in": 3600,
            "scope": "Workspace.Read.All",
        },
    )

    monkeypatch.setattr(
        service_module,
        "FabricClient",
        lambda: FailingFabricClient(),
    )

    session = DeviceAuthSession(
        tenant_id="tenant",
        client_id="client",
    )

    service = MicrosoftDeviceAuthService()

    await service._try_acquire_fabric_token(
        app=app,
        session=session,
    )

    assert session.fabric_access_token is None
    assert session.fabric_connected is False
    assert session.fabric_error_code == "AUTH_INSUFFICIENT_PERMISSIONS"
    assert session.fabric_granted_scopes == []
