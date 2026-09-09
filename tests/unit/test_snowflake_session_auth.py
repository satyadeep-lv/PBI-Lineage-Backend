import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.clients.snowflake_session_client import SnowflakeSessionClient
from app.core.exceptions import (
    InvalidLineageRequestError,
    ProviderAuthenticationFailedError,
)
from app.schemas.snowflake_auth import (
    SnowflakeExternalBrowserAuthenticationRequest,
    SnowflakeKeyPairAuthenticationRequest,
    SnowflakeOAuthAuthenticationRequest,
    SnowflakePasswordAuthenticationRequest,
)
from app.services.auth.snowflake_session_store import (
    SnowflakeSessionIdentity,
    SnowflakeSessionStore,
)


class _Connection:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _IdentityCursor:
    def __init__(self) -> None:
        self.executed = False
        self.closed = False

    def execute(self, query: str) -> None:
        self.executed = "CURRENT_ACCOUNT" in query

    def fetchone(self):
        return (
            "ORG_ACCOUNT",
            "LINEAGE_USER",
            "LINEAGE_READER",
            "LINEAGE_WH",
            "ANALYTICS",
            "PUBLIC",
        )

    def close(self) -> None:
        self.closed = True


class _ConnectedSession(_Connection):
    def __init__(self) -> None:
        super().__init__()
        self.identity_cursor = _IdentityCursor()

    def cursor(self):
        return self.identity_cursor


class _Connector:
    def __init__(self, connection=None, error: Exception | None = None) -> None:
        self.connection = connection
        self.error = error
        self.parameters = None

    def connect(self, **parameters):
        self.parameters = parameters
        if self.error is not None:
            raise self.error
        return self.connection


def _options() -> dict[str, str]:
    return {
        "account_identifier": "organization-account",
        "user": "lineage_user",
        "warehouse": "LINEAGE_WH",
        "database": "ANALYTICS",
        "schema_name": "PUBLIC",
        "role": "LINEAGE_READER",
    }


def test_password_authentication_maps_password_and_mfa_options():
    request = SnowflakePasswordAuthenticationRequest(
        **_options(),
        authentication_method="password",
        password="secret-password",
        authenticator="username_password_mfa",
        passcode="123456",
    )

    parameters = SnowflakeSessionClient()._connection_parameters(request)

    assert parameters["password"] == "secret-password"
    assert parameters["authenticator"] == "username_password_mfa"
    assert parameters["passcode"] == "123456"
    assert parameters["schema"] == "PUBLIC"
    assert "secret-password" not in request.model_dump_json()


def test_key_pair_authentication_decodes_encrypted_rsa_key_in_memory():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(b"key-passphrase"),
    ).decode("ascii")
    request = SnowflakeKeyPairAuthenticationRequest(
        **_options(),
        authentication_method="key_pair",
        private_key_pem=pem,
        private_key_passphrase="key-passphrase",
    )

    parameters = SnowflakeSessionClient()._connection_parameters(request)

    assert parameters["authenticator"] == "SNOWFLAKE_JWT"
    assert isinstance(parameters["private_key"], bytes)
    assert b"BEGIN" not in parameters["private_key"]


def test_oauth_authentication_uses_external_access_token():
    request = SnowflakeOAuthAuthenticationRequest(
        **_options(),
        authentication_method="oauth",
        token="oauth-secret-token",
    )

    parameters = SnowflakeSessionClient()._connection_parameters(request)

    assert parameters["authenticator"] == "oauth"
    assert parameters["token"] == "oauth-secret-token"
    assert "oauth-secret-token" not in request.model_dump_json()


def test_external_browser_requires_explicit_runtime_enablement():
    request = SnowflakeExternalBrowserAuthenticationRequest(
        **_options(),
        authentication_method="external_browser",
    )

    with pytest.raises(InvalidLineageRequestError, match="disabled"):
        SnowflakeSessionClient()._connection_parameters(request)

    parameters = SnowflakeSessionClient(
        allow_external_browser=True
    )._connection_parameters(request)
    assert parameters["authenticator"] == "externalbrowser"


def test_session_client_connects_and_reads_sanitized_identity(monkeypatch):
    connection = _ConnectedSession()
    connector = _Connector(connection=connection)
    client = SnowflakeSessionClient()
    monkeypatch.setattr(client, "_connector_module", lambda: connector)
    request = SnowflakePasswordAuthenticationRequest(
        **_options(),
        authentication_method="password",
        password="secret-password",
    )

    connected, identity = client.connect(request)

    assert connected is connection
    assert connector.parameters["application"] == "PBI_LINEAGE_BACKEND"
    assert connector.parameters["password"] == "secret-password"
    assert connection.identity_cursor.executed is True
    assert connection.identity_cursor.closed is True
    assert identity.current_account == "ORG_ACCOUNT"
    assert identity.current_role == "LINEAGE_READER"


def test_session_client_does_not_expose_connector_failure_details(monkeypatch):
    connector = _Connector(error=RuntimeError("secret-password"))
    client = SnowflakeSessionClient()
    monkeypatch.setattr(client, "_connector_module", lambda: connector)
    request = SnowflakePasswordAuthenticationRequest(
        **_options(),
        authentication_method="password",
        password="secret-password",
    )

    with pytest.raises(ProviderAuthenticationFailedError) as exc_info:
        client.connect(request)

    assert "secret-password" not in str(exc_info.value)


def test_session_store_closes_deleted_connection_after_active_checkout():
    now = [100.0]
    store = SnowflakeSessionStore(max_age_seconds=60, clock=lambda: now[0])
    connection = _Connection()
    identity = SnowflakeSessionIdentity(
        authentication_method="password",
        account_identifier="organization-account",
        user="lineage_user",
    )
    session = store.save(connection, identity)

    with store.checkout(session.session_id):
        assert store.delete(session.session_id) is True
        assert connection.closed == 0

    assert connection.closed == 1
    assert store.get(session.session_id) is None


def test_session_store_expires_and_closes_idle_connection():
    now = [100.0]
    store = SnowflakeSessionStore(max_age_seconds=60, clock=lambda: now[0])
    connection = _Connection()
    session = store.save(
        connection,
        SnowflakeSessionIdentity(
            authentication_method="oauth",
            account_identifier="organization-account",
            user="lineage_user",
        ),
    )

    now[0] = 161.0

    assert store.get(session.session_id) is None
    assert connection.closed == 1


def test_session_store_close_all_defers_active_connection_cleanup():
    store = SnowflakeSessionStore(max_age_seconds=60)
    active_connection = _Connection()
    idle_connection = _Connection()
    identity = SnowflakeSessionIdentity(
        authentication_method="password",
        account_identifier="organization-account",
        user="lineage_user",
    )
    active_session = store.save(active_connection, identity)
    idle_session = store.save(idle_connection, identity)

    with store.checkout(active_session.session_id):
        store.close_all()
        assert active_connection.closed == 0
        assert idle_connection.closed == 1
        assert store.get(idle_session.session_id) is None

    assert active_connection.closed == 1
