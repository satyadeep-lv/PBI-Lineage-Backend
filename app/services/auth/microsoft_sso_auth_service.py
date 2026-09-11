import asyncio
from time import time
from uuid import uuid4

import msal

from app.clients.powerbi_client import PowerBIClient
from app.core.exceptions import (
    AuthenticationStateInvalidError,
    ProviderAuthenticationFailedError,
)
from app.core.microsoft_auth import (
    MICROSOFT_LOGIN_BASE_URL,
    POWERBI_SCOPES,
    extract_granted_scopes,
    generate_pkce_pair,
)
from app.services.auth.device_auth_store import (
    DeviceAuthSession,
    save_device_session,
)
from app.services.auth.microsoft_device_auth_service import (
    MicrosoftDeviceAuthService,
)
from app.services.auth.sso_login_store import (
    PendingSsoLogin,
    pop_pending_sso_login,
    save_pending_sso_login,
)


class MicrosoftSsoAuthService:
    def build_authorization_url(
        self,
        *,
        tenant_id: str,
        client_id: str,
        redirect_uri: str,
        post_login_redirect_uri: str | None,
    ) -> str:
        code_verifier, code_challenge = generate_pkce_pair()
        state = uuid4().hex

        app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"{MICROSOFT_LOGIN_BASE_URL}/{tenant_id}",
        )

        authorization_url = app.get_authorization_request_url(
            scopes=POWERBI_SCOPES,
            state=state,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )

        save_pending_sso_login(
            state,
            PendingSsoLogin(
                tenant_id=tenant_id,
                client_id=client_id,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
                post_login_redirect_uri=post_login_redirect_uri,
            ),
        )

        return authorization_url

    async def complete_login(
        self,
        *,
        code: str,
        state: str,
    ) -> tuple[str, str | None]:
        pending = pop_pending_sso_login(state)

        if pending is None:
            raise AuthenticationStateInvalidError()

        app = msal.PublicClientApplication(
            client_id=pending.client_id,
            authority=f"{MICROSOFT_LOGIN_BASE_URL}/{pending.tenant_id}",
        )

        result = await asyncio.to_thread(
            app.acquire_token_by_authorization_code,
            code,
            scopes=POWERBI_SCOPES,
            redirect_uri=pending.redirect_uri,
            code_verifier=pending.code_verifier,
        )

        access_token = result.get("access_token")

        if not access_token:
            raise ProviderAuthenticationFailedError("powerbi")

        await PowerBIClient().validate_connection(access_token)

        expires_in = int(result.get("expires_in", 3600))
        powerbi_expires_at = time() + max(expires_in - 60, 60)

        session = DeviceAuthSession(
            tenant_id=pending.tenant_id,
            client_id=pending.client_id,
            authentication_method="sso",
            status="authenticated",
            powerbi_access_token=access_token,
            powerbi_token_expires_at=powerbi_expires_at,
            powerbi_connected=True,
            powerbi_granted_scopes=extract_granted_scopes(result),
        )

        await MicrosoftDeviceAuthService._try_acquire_fabric_token(
            app=app,
            session=session,
        )

        session_id = str(uuid4())
        save_device_session(session_id, session)

        return session_id, pending.post_login_redirect_uri
