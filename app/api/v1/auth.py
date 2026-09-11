from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, Response
from fastapi.responses import RedirectResponse

from app.api.dependencies.security import require_lineage_api_key
from app.core.auth_session import (
    AUTH_SESSION_COOKIE,
    AUTH_SESSION_MAX_AGE_SECONDS,
)
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationRedirectNotAllowedError,
    AuthenticationSessionExpiredError,
    AuthenticationSessionRequiredError,
    ProviderAuthenticationFailedError,
    ProviderIntegrationNotConfiguredError,
)
from app.core.microsoft_auth import (
    FABRIC_SCOPES,
    POWERBI_SCOPES,
    get_scope_permission,
    normalize_scope_permissions,
)
from app.schemas.auth import (
    MicrosoftDeviceAuthRequest,
    MicrosoftDeviceAuthStartResponse,
    MicrosoftDeviceAuthStatusResponse,
    MicrosoftServicePrincipalAuthRequest,
    MicrosoftServicePrincipalAuthResponse,
    ProviderScopeAccess,
    ProviderTestResult,
)
from app.services.auth.device_auth_store import (
    DeviceAuthSession,
    delete_device_session,
    get_device_session,
)
from app.services.auth.microsoft_device_auth_service import (
    MicrosoftDeviceAuthService,
)
from app.services.auth.microsoft_service_principal_auth_service import (
    MicrosoftServicePrincipalAuthService,
)
from app.services.auth.microsoft_sso_auth_service import (
    MicrosoftSsoAuthService,
)
from app.services.auth.sso_login_store import pop_pending_sso_login

router = APIRouter()


def _require_allowed_redirect_origin(
    redirect_uri: str,
    allowed_origins: list[str],
) -> None:
    parsed = urlsplit(redirect_uri)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    if not parsed.scheme or not parsed.netloc or origin not in allowed_origins:
        raise AuthenticationRedirectNotAllowedError()


def _build_scope_access(
    *,
    requested_scopes: list[str],
    granted_scopes: list[str],
) -> list[ProviderScopeAccess]:
    granted_permissions = set(normalize_scope_permissions(granted_scopes))

    return [
        ProviderScopeAccess(
            scope=scope,
            permission=get_scope_permission(scope),
            granted=(get_scope_permission(scope) in granted_permissions),
        )
        for scope in requested_scopes
    ]


def _build_provider_test_result(
    *,
    connected: bool,
    success_message: str,
    failure_message: str,
    requested_scopes: list[str],
    granted_scopes: list[str],
    error_code: str | None = None,
) -> ProviderTestResult:
    scope_access = _build_scope_access(
        requested_scopes=requested_scopes,
        granted_scopes=granted_scopes,
    )

    missing_scopes = [item.scope for item in scope_access if not item.granted]

    message = success_message if connected else failure_message

    if not connected and error_code:
        message = f"{message}: {error_code}"

    return ProviderTestResult(
        connected=connected,
        message=message,
        error_code=error_code,
        requested_scopes=requested_scopes,
        granted_scopes=normalize_scope_permissions(granted_scopes),
        missing_scopes=missing_scopes,
        scope_access=scope_access,
    )


def _build_device_status_response(
    session: DeviceAuthSession,
) -> MicrosoftDeviceAuthStatusResponse:
    if session.status == "pending":
        return MicrosoftDeviceAuthStatusResponse(
            status="pending",
            powerbi=_build_provider_test_result(
                connected=False,
                success_message=("Power BI connection successful."),
                failure_message=("Power BI authentication is pending."),
                requested_scopes=POWERBI_SCOPES,
                granted_scopes=[],
            ),
            fabric=_build_provider_test_result(
                connected=False,
                success_message=("Fabric connection successful."),
                failure_message=("Fabric authentication is pending."),
                requested_scopes=FABRIC_SCOPES,
                granted_scopes=[],
            ),
            message=("Waiting for Microsoft authentication."),
        )

    if session.status == "failed":
        return MicrosoftDeviceAuthStatusResponse(
            status="failed",
            powerbi=_build_provider_test_result(
                connected=False,
                success_message=("Power BI connection successful."),
                failure_message=("Power BI connection failed."),
                requested_scopes=POWERBI_SCOPES,
                granted_scopes=(session.powerbi_granted_scopes),
                error_code=(session.powerbi_error_code),
            ),
            fabric=_build_provider_test_result(
                connected=False,
                success_message=("Fabric connection successful."),
                failure_message=("Fabric authentication is not available."),
                requested_scopes=FABRIC_SCOPES,
                granted_scopes=(session.fabric_granted_scopes),
                error_code=(session.fabric_error_code),
            ),
            message=session.error_message,
        )

    return MicrosoftDeviceAuthStatusResponse(
        status="authenticated",
        powerbi=_build_provider_test_result(
            connected=bool(session.powerbi_connected),
            success_message=("Power BI connection successful."),
            failure_message=("Power BI connection failed."),
            requested_scopes=POWERBI_SCOPES,
            granted_scopes=(session.powerbi_granted_scopes),
            error_code=session.powerbi_error_code,
        ),
        fabric=_build_provider_test_result(
            connected=bool(session.fabric_connected),
            success_message=("Fabric connection successful."),
            failure_message=("Fabric authentication is not available."),
            requested_scopes=FABRIC_SCOPES,
            granted_scopes=(session.fabric_granted_scopes),
            error_code=session.fabric_error_code,
        ),
        message=None,
    )


@router.get(
    "/microsoft/device/{session_id}/status",
    response_model=MicrosoftDeviceAuthStatusResponse,
)
async def get_microsoft_device_authentication_status(
    session_id: str,
) -> MicrosoftDeviceAuthStatusResponse:
    session = get_device_session(session_id)

    if session is None:
        return MicrosoftDeviceAuthStatusResponse(
            status="expired",
            message=("Authentication session does not exist or has expired."),
        )

    return _build_device_status_response(session)


@router.post(
    "/microsoft/device/start",
    response_model=(MicrosoftDeviceAuthStartResponse),
)
async def start_microsoft_device_authentication(
    request: MicrosoftDeviceAuthRequest,
    response: Response,
) -> MicrosoftDeviceAuthStartResponse:
    settings = get_settings()
    service = MicrosoftDeviceAuthService()

    session_id, flow = await service.start(
        tenant_id=request.tenant_id,
        client_id=request.client_id,
    )

    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=session_id,
        max_age=(AUTH_SESSION_MAX_AGE_SECONDS),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )

    return MicrosoftDeviceAuthStartResponse(
        session_id=session_id,
        verification_uri=flow["verification_uri"],
        user_code=flow["user_code"],
        message=flow["message"],
        expires_in=int(
            flow.get(
                "expires_in",
                900,
            )
        ),
    )


@router.get(
    "/microsoft/device/status",
    response_model=MicrosoftDeviceAuthStatusResponse,
)
async def get_microsoft_device_auth_status(
    session_id: str | None = Cookie(
        default=None,
        alias=AUTH_SESSION_COOKIE,
    ),
) -> MicrosoftDeviceAuthStatusResponse:

    if session_id is None:
        raise AuthenticationSessionRequiredError()

    session = get_device_session(session_id)

    if session is None:
        raise AuthenticationSessionExpiredError()

    if session.status == "pending":
        return _build_device_status_response(session)

    if session.status == "failed":
        return _build_device_status_response(session)

    return _build_device_status_response(session)


@router.post(
    "/microsoft/device/logout",
)
async def logout_microsoft_device_session(
    response: Response,
    session_id: str | None = Cookie(
        default=None,
        alias=AUTH_SESSION_COOKIE,
    ),
) -> dict[str, str]:
    settings = get_settings()

    if session_id:
        delete_device_session(session_id)

    response.delete_cookie(
        key=AUTH_SESSION_COOKIE,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )

    return {"status": "logged_out"}


@router.get(
    "/microsoft/sso/login",
)
async def start_microsoft_sso_login(
    tenant_id: str,
    client_id: str,
    post_login_redirect_uri: str | None = None,
) -> RedirectResponse:
    settings = get_settings()

    if not settings.microsoft_sso_redirect_uri:
        raise ProviderIntegrationNotConfiguredError(
            "powerbi",
            detail="MICROSOFT_SSO_REDIRECT_URI is not configured.",
        )

    if post_login_redirect_uri:
        _require_allowed_redirect_origin(
            post_login_redirect_uri,
            settings.cors_allowed_origins,
        )

    authorization_url = MicrosoftSsoAuthService().build_authorization_url(
        tenant_id=tenant_id,
        client_id=client_id,
        redirect_uri=settings.microsoft_sso_redirect_uri,
        post_login_redirect_uri=post_login_redirect_uri,
    )

    return RedirectResponse(
        url=authorization_url,
        status_code=307,
    )


@router.get(
    "/microsoft/sso/callback",
    response_model=None,
)
async def complete_microsoft_sso_login(
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse | MicrosoftDeviceAuthStatusResponse:
    if error or not code or not state:
        if state:
            pop_pending_sso_login(state)

        raise ProviderAuthenticationFailedError("powerbi")

    settings = get_settings()

    (
        session_id,
        post_login_redirect_uri,
    ) = await MicrosoftSsoAuthService().complete_login(
        code=code,
        state=state,
    )

    cookie_kwargs: dict[str, object] = {
        "key": AUTH_SESSION_COOKIE,
        "value": session_id,
        "max_age": AUTH_SESSION_MAX_AGE_SECONDS,
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "path": "/",
    }

    if post_login_redirect_uri:
        redirect = RedirectResponse(
            url=post_login_redirect_uri,
            status_code=307,
        )
        redirect.set_cookie(**cookie_kwargs)
        return redirect

    response.set_cookie(**cookie_kwargs)

    session = get_device_session(session_id)

    if session is None:
        raise AuthenticationSessionExpiredError()

    return _build_device_status_response(session)


@router.post(
    "/microsoft/service-principal/session",
    response_model=MicrosoftServicePrincipalAuthResponse,
    dependencies=[Depends(require_lineage_api_key)],
)
async def authenticate_microsoft_service_principal(
    request: MicrosoftServicePrincipalAuthRequest,
    response: Response,
    previous_session_id: str | None = Cookie(
        default=None,
        alias=AUTH_SESSION_COOKIE,
    ),
) -> MicrosoftServicePrincipalAuthResponse:
    settings = get_settings()
    service = MicrosoftServicePrincipalAuthService()
    result = await service.authenticate(
        tenant_id=request.tenant_id,
        client_id=request.client_id,
        client_secret=request.client_secret.get_secret_value(),
    )

    if previous_session_id and previous_session_id != result.session_id:
        delete_device_session(previous_session_id)

    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=result.session_id,
        max_age=AUTH_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
    return result


@router.get(
    "/microsoft/service-principal/session/status",
    response_model=MicrosoftServicePrincipalAuthResponse,
    dependencies=[Depends(require_lineage_api_key)],
)
async def get_microsoft_service_principal_status(
    session_id: str | None = Cookie(
        default=None,
        alias=AUTH_SESSION_COOKIE,
    ),
) -> MicrosoftServicePrincipalAuthResponse:
    if session_id is None:
        raise AuthenticationSessionRequiredError()
    return MicrosoftServicePrincipalAuthService().status(session_id)


@router.delete(
    "/microsoft/service-principal/session",
    dependencies=[Depends(require_lineage_api_key)],
)
async def logout_microsoft_service_principal(
    response: Response,
    session_id: str | None = Cookie(
        default=None,
        alias=AUTH_SESSION_COOKIE,
    ),
) -> dict[str, str]:
    settings = get_settings()
    if session_id:
        delete_device_session(session_id)
    response.delete_cookie(
        key=AUTH_SESSION_COOKIE,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )
    return {"status": "logged_out"}
