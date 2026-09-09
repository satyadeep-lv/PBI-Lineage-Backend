import asyncio
from time import time
from typing import Any
from uuid import uuid4

import msal

from app.core.exceptions import (
    AuthenticationSessionExpiredError,
    AuthenticationSessionRequiredError,
    InvalidAccessTokenError,
    ProviderAuthenticationFailedError,
)
from app.core.microsoft_auth import (
    FABRIC_APPLICATION_SCOPE,
    FABRIC_RESOURCE,
    MICROSOFT_LOGIN_BASE_URL,
    POWERBI_APPLICATION_SCOPE,
    POWERBI_RESOURCE,
    extract_granted_scopes,
)
from app.schemas.auth import (
    MicrosoftApplicationTokenResult,
    MicrosoftServicePrincipalAuthResponse,
)
from app.services.auth.device_auth_store import (
    DeviceAuthSession,
    get_device_session,
    get_fabric_token,
    get_powerbi_token,
    save_device_session,
)


class MicrosoftServicePrincipalAuthService:
    @staticmethod
    def _error_code(
        result: dict[str, Any],
        *,
        fallback: str,
    ) -> str:
        error = result.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()[:128]
        return fallback

    @staticmethod
    def _expires_at(result: dict[str, Any]) -> float:
        expires_in = result.get("expires_in", 3600)
        try:
            lifetime_seconds = int(expires_in)
        except (TypeError, ValueError):
            lifetime_seconds = 3600
        return time() + max(lifetime_seconds - 60, 60)

    @staticmethod
    def _acquire_token_sync(
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        scope: str,
    ) -> dict[str, Any]:
        application = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=(f"{MICROSOFT_LOGIN_BASE_URL}/{tenant_id}"),
        )
        result = application.acquire_token_for_client(scopes=[scope])
        if not isinstance(result, dict):
            return {"error": "invalid_token_response"}
        return result

    async def _acquire_token(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        scope: str,
    ) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                self._acquire_token_sync,
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
                scope=scope,
            )
        # MSAL can surface transport-library exceptions from this SDK boundary.
        except Exception:  # noqa: BLE001
            return {"error": "token_request_failed"}

    async def authenticate(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ) -> MicrosoftServicePrincipalAuthResponse:
        powerbi_result, fabric_result = await asyncio.gather(
            self._acquire_token(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
                scope=POWERBI_APPLICATION_SCOPE,
            ),
            self._acquire_token(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
                scope=FABRIC_APPLICATION_SCOPE,
            ),
        )

        powerbi_token = powerbi_result.get("access_token")
        if not isinstance(powerbi_token, str) or not powerbi_token:
            raise ProviderAuthenticationFailedError("powerbi")

        fabric_token = fabric_result.get("access_token")
        fabric_connected = isinstance(fabric_token, str) and bool(fabric_token)
        fabric_error_code = None
        if not fabric_connected:
            fabric_error_code = self._error_code(
                fabric_result,
                fallback="fabric_authentication_failed",
            )

        session_id = str(uuid4())
        save_device_session(
            session_id,
            DeviceAuthSession(
                tenant_id=tenant_id,
                client_id=client_id,
                authentication_method="client_secret",
                status="authenticated",
                powerbi_access_token=powerbi_token,
                powerbi_token_expires_at=self._expires_at(powerbi_result),
                fabric_access_token=(fabric_token if fabric_connected else None),
                fabric_token_expires_at=(
                    self._expires_at(fabric_result) if fabric_connected else None
                ),
                powerbi_connected=True,
                fabric_connected=fabric_connected,
                powerbi_granted_scopes=(extract_granted_scopes(powerbi_result)),
                fabric_granted_scopes=(
                    extract_granted_scopes(fabric_result) if fabric_connected else []
                ),
                fabric_error_code=fabric_error_code,
            ),
        )
        return self.status(session_id)

    def status(
        self,
        session_id: str,
    ) -> MicrosoftServicePrincipalAuthResponse:
        session = get_device_session(session_id)
        if session is None:
            raise AuthenticationSessionExpiredError()
        if session.authentication_method != "client_secret":
            raise AuthenticationSessionRequiredError()

        powerbi_acquired = get_powerbi_token(session_id) is not None
        fabric_acquired = get_fabric_token(session_id) is not None
        if not powerbi_acquired:
            raise InvalidAccessTokenError("powerbi")
        status = "authenticated" if fabric_acquired else "partial"

        return MicrosoftServicePrincipalAuthResponse(
            session_id=session_id,
            status=status,
            powerbi=MicrosoftApplicationTokenResult(
                token_acquired=powerbi_acquired,
                resource=POWERBI_RESOURCE,
                requested_scope=POWERBI_APPLICATION_SCOPE,
                granted_roles=list(session.powerbi_granted_scopes),
                error_code=session.powerbi_error_code,
                message=(
                    "Power BI application token acquired."
                    if powerbi_acquired
                    else "Power BI application token is unavailable."
                ),
            ),
            fabric=MicrosoftApplicationTokenResult(
                token_acquired=fabric_acquired,
                resource=FABRIC_RESOURCE,
                requested_scope=FABRIC_APPLICATION_SCOPE,
                granted_roles=list(session.fabric_granted_scopes),
                error_code=session.fabric_error_code,
                message=(
                    "Fabric application token acquired."
                    if fabric_acquired
                    else "Fabric application token is unavailable."
                ),
            ),
            message=(
                None
                if fabric_acquired
                else (
                    "Power BI authentication succeeded, but Fabric "
                    "authentication is not available."
                )
            ),
        )
