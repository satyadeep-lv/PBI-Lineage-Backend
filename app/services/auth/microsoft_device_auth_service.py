import asyncio
from time import time
from uuid import uuid4

import msal

from app.clients.fabric_client import FabricClient
from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import AppException
from app.core.microsoft_auth import (
    FABRIC_SCOPES,
    MICROSOFT_LOGIN_BASE_URL,
    POWERBI_SCOPES,
    extract_granted_scopes,
)
from app.services.auth.device_auth_store import (
    DeviceAuthSession,
    get_device_session,
    save_device_session,
)


class MicrosoftDeviceAuthService:
    async def _wait_for_authentication(
        self,
        *,
        session_id: str,
    ) -> None:
        session = get_device_session(session_id)

        if session is None:
            return

        authority = f"{MICROSOFT_LOGIN_BASE_URL}/{session.tenant_id}"

        app = msal.PublicClientApplication(
            client_id=session.client_id,
            authority=authority,
        )

        result = await asyncio.to_thread(
            app.acquire_token_by_device_flow,
            session.flow,
        )

        access_token = result.get("access_token")

        if not access_token:
            error_code = str(
                result.get(
                    "error",
                    "authentication_failed",
                )
            )

            session.status = "failed"
            session.powerbi_connected = False
            session.powerbi_error_code = error_code
            session.error_message = error_code

            return

        expires_in = int(
            result.get(
                "expires_in",
                3600,
            )
        )

        powerbi_expires_at = time() + max(
            expires_in - 60,
            60,
        )

        powerbi_client = PowerBIClient()

        try:
            await powerbi_client.validate_connection(access_token)
        except AppException as exc:
            session.status = "failed"
            session.powerbi_access_token = None
            session.powerbi_token_expires_at = None
            session.powerbi_connected = False
            session.powerbi_granted_scopes.clear()
            session.powerbi_error_code = exc.code
            session.error_message = exc.message
            return

        session.powerbi_access_token = access_token
        session.powerbi_token_expires_at = powerbi_expires_at
        session.powerbi_connected = True
        session.powerbi_error_code = None
        session.error_message = None
        session.powerbi_granted_scopes = extract_granted_scopes(result)
        session.status = "authenticated"

        try:
            await self._try_acquire_fabric_token(
                app=app,
                session=session,
            )
        finally:
            session.flow.clear()

    async def _wait_for_fabric_authentication(
        self,
        *,
        session_id: str,
    ) -> None:
        session = get_device_session(session_id)

        if session is None:
            return

        authority = f"{MICROSOFT_LOGIN_BASE_URL}/{session.tenant_id}"

        app = msal.PublicClientApplication(
            client_id=session.client_id,
            authority=authority,
        )

        result = await asyncio.to_thread(
            app.acquire_token_by_device_flow,
            session.fabric_flow,
        )

        access_token = result.get("access_token")

        if not access_token:
            error_code = str(
                result.get(
                    "error",
                    "fabric_authentication_failed",
                )
            )

            session.fabric_access_token = None
            session.fabric_token_expires_at = None
            session.fabric_connected = False
            session.fabric_granted_scopes.clear()
            session.fabric_error_code = error_code

            return

        expires_in = int(
            result.get(
                "expires_in",
                3600,
            )
        )

        expires_at = time() + max(
            expires_in - 60,
            60,
        )

        fabric_client = FabricClient()

        try:
            await fabric_client.validate_connection(access_token)
        except AppException as exc:
            session.fabric_access_token = None
            session.fabric_token_expires_at = None
            session.fabric_connected = False
            session.fabric_granted_scopes.clear()
            session.fabric_error_code = exc.code
            return

        session.fabric_access_token = access_token
        session.fabric_token_expires_at = expires_at
        session.fabric_granted_scopes = extract_granted_scopes(result)
        session.fabric_connected = True
        session.fabric_error_code = None
        session.fabric_flow.clear()

    async def _try_acquire_fabric_token(
        self,
        *,
        app: msal.PublicClientApplication,
        session: DeviceAuthSession,
    ) -> None:
        accounts = app.get_accounts()
        try:
            if not accounts:
                session.fabric_connected = False
                session.fabric_error_code = "account_not_cached"
                session.fabric_granted_scopes.clear()
                return

            account = accounts[0]

            result = await asyncio.to_thread(
                app.acquire_token_silent_with_error,
                FABRIC_SCOPES,
                account=account,
            )

            if not result:
                session.fabric_connected = False
                session.fabric_granted_scopes.clear()
                session.fabric_error_code = "interaction_required"

                return

            access_token = result.get("access_token")

            if not access_token:
                session.fabric_connected = False

                session.fabric_error_code = result.get(
                    "error",
                    "interaction_required",
                )

                session.fabric_granted_scopes.clear()

                return

            expires_in = int(
                result.get(
                    "expires_in",
                    3600,
                )
            )

            expires_at = time() + max(
                expires_in - 60,
                60,
            )

            fabric_client = FabricClient()

            await fabric_client.validate_connection(access_token)

            session.fabric_access_token = access_token

            session.fabric_token_expires_at = expires_at

            session.fabric_granted_scopes = extract_granted_scopes(result)

            session.fabric_connected = True
            session.fabric_error_code = None
        except AppException as exc:
            session.fabric_access_token = None
            session.fabric_token_expires_at = None
            session.fabric_connected = False
            session.fabric_error_code = exc.code
            session.fabric_granted_scopes.clear()

    async def start(
        self,
        *,
        tenant_id: str,
        client_id: str,
    ) -> tuple[str, dict]:
        authority = f"{MICROSOFT_LOGIN_BASE_URL}/{tenant_id}"

        app = msal.PublicClientApplication(
            client_id=client_id,
            authority=authority,
        )

        flow = app.initiate_device_flow(
            scopes=POWERBI_SCOPES,
        )

        if "user_code" not in flow:
            raise RuntimeError("Microsoft device authentication could not be started.")

        session_id = str(uuid4())

        save_device_session(
            session_id,
            DeviceAuthSession(
                tenant_id=tenant_id,
                client_id=client_id,
                flow=flow,
            ),
        )

        asyncio.create_task(
            self._wait_for_authentication(
                session_id=session_id,
            )
        )

        return session_id, flow

    async def start_fabric_authentication(
        self,
        *,
        session_id: str,
    ) -> dict:
        session = get_device_session(session_id)

        if session is None:
            raise RuntimeError("Authentication session does not exist.")

        authority = f"{MICROSOFT_LOGIN_BASE_URL}/{session.tenant_id}"

        app = msal.PublicClientApplication(
            client_id=session.client_id,
            authority=authority,
        )

        flow = app.initiate_device_flow(
            scopes=FABRIC_SCOPES,
        )

        if "user_code" not in flow:
            raise RuntimeError("Fabric authentication could not be started.")

        session.fabric_flow = flow

        asyncio.create_task(
            self._wait_for_fabric_authentication(
                session_id=session_id,
            )
        )

        return flow
