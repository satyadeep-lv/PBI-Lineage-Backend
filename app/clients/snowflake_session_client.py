import importlib
import re
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.exceptions import (
    InvalidLineageRequestError,
    ProviderAuthenticationFailedError,
    ProviderIntegrationNotConfiguredError,
)
from app.schemas.snowflake_auth import (
    SnowflakeAuthenticationRequest,
    SnowflakeExternalBrowserAuthenticationRequest,
    SnowflakeKeyPairAuthenticationRequest,
    SnowflakeOAuthAuthenticationRequest,
    SnowflakePasswordAuthenticationRequest,
)
from app.services.auth.snowflake_session_store import (
    SnowflakeConnection,
    SnowflakeSessionIdentity,
)

_ACCOUNT_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SnowflakeSessionClient:
    def __init__(self, *, allow_external_browser: bool = False) -> None:
        self.allow_external_browser = allow_external_browser

    def connect(
        self,
        request: SnowflakeAuthenticationRequest,
    ) -> tuple[SnowflakeConnection, SnowflakeSessionIdentity]:
        connector = self._connector_module()
        parameters = self._connection_parameters(request)
        connection = None
        try:
            connection = connector.connect(**parameters)
            identity = self._identity(connection, request)
        except (InvalidLineageRequestError, ProviderIntegrationNotConfiguredError):
            if connection is not None:
                self._close(connection)
            raise
        except Exception as exc:
            if connection is not None:
                self._close(connection)
            raise ProviderAuthenticationFailedError("snowflake") from exc
        return connection, identity

    def _connection_parameters(
        self,
        request: SnowflakeAuthenticationRequest,
    ) -> dict[str, Any]:
        if not _ACCOUNT_IDENTIFIER_PATTERN.fullmatch(request.account_identifier):
            raise InvalidLineageRequestError(
                "Snowflake account_identifier must not contain a URL or path."
            )

        parameters: dict[str, Any] = {
            "account": request.account_identifier,
            "user": request.user,
            "warehouse": request.warehouse,
            "database": request.database,
            "schema": request.schema_name,
            "role": request.role,
            "application": "PBI_LINEAGE_BACKEND",
            "login_timeout": 30,
            "network_timeout": 60,
            "session_parameters": {"QUERY_TAG": "PBI_LINEAGE_BACKEND"},
        }

        if isinstance(request, SnowflakePasswordAuthenticationRequest):
            parameters.update(
                password=request.password.get_secret_value(),
                authenticator=request.authenticator,
                passcode=(
                    request.passcode.get_secret_value()
                    if request.passcode is not None
                    else None
                ),
                passcode_in_password=request.passcode_in_password,
            )
        elif isinstance(request, SnowflakeKeyPairAuthenticationRequest):
            parameters.update(
                authenticator="SNOWFLAKE_JWT",
                private_key=self._private_key_der(request),
            )
        elif isinstance(request, SnowflakeExternalBrowserAuthenticationRequest):
            if not self.allow_external_browser:
                raise InvalidLineageRequestError(
                    "External-browser Snowflake authentication is disabled on "
                    "this host. Enable it only for an interactive local runtime, "
                    "or use OAuth for hosted authentication."
                )
            parameters["authenticator"] = "externalbrowser"
        elif isinstance(request, SnowflakeOAuthAuthenticationRequest):
            parameters.update(
                authenticator="oauth",
                token=request.token.get_secret_value(),
            )

        return {key: value for key, value in parameters.items() if value is not None}

    @staticmethod
    def _private_key_der(
        request: SnowflakeKeyPairAuthenticationRequest,
    ) -> bytes:
        pem = request.private_key_pem.get_secret_value()
        if "\n" not in pem and "\\n" in pem:
            pem = pem.replace("\\n", "\n")
        password = (
            request.private_key_passphrase.get_secret_value().encode("utf-8")
            if request.private_key_passphrase is not None
            else None
        )
        try:
            private_key = serialization.load_pem_private_key(
                pem.encode("utf-8"),
                password=password,
            )
        except (TypeError, ValueError) as exc:
            raise InvalidLineageRequestError(
                "The RSA private key or private-key passphrase is invalid."
            ) from exc
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise InvalidLineageRequestError(
                "Snowflake key-pair authentication requires an RSA private key."
            )
        return private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @staticmethod
    def _identity(
        connection: SnowflakeConnection,
        request: SnowflakeAuthenticationRequest,
    ) -> SnowflakeSessionIdentity:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE(), "
                "CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()"
            )
            row = cursor.fetchone()
        finally:
            SnowflakeSessionClient._close(cursor)
        values = list(row or ()) + [None] * 6
        return SnowflakeSessionIdentity(
            authentication_method=request.authentication_method,
            account_identifier=request.account_identifier,
            user=request.user,
            current_account=SnowflakeSessionClient._optional_text(values[0]),
            current_user=SnowflakeSessionClient._optional_text(values[1]),
            current_role=SnowflakeSessionClient._optional_text(values[2]),
            current_warehouse=SnowflakeSessionClient._optional_text(values[3]),
            current_database=SnowflakeSessionClient._optional_text(values[4]),
            current_schema=SnowflakeSessionClient._optional_text(values[5]),
        )

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return None if value is None else str(value)

    @staticmethod
    def _connector_module() -> Any:
        try:
            return importlib.import_module("snowflake.connector")
        except ImportError as exc:
            raise ProviderIntegrationNotConfiguredError(
                "snowflake",
                detail="Install the snowflake-connector-python dependency.",
            ) from exc

    @staticmethod
    def _close(connection: SnowflakeConnection) -> None:
        try:
            connection.close()
        except Exception:  # noqa: BLE001 - failed authentication cleanup
            return
