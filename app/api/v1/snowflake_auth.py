import asyncio

from fastapi import APIRouter, Cookie, Depends, Response

from app.api.dependencies.security import require_lineage_api_key
from app.core.config import get_settings
from app.core.exceptions import ProviderAuthenticationRequiredError
from app.schemas.snowflake_auth import (
    SnowflakeAuthenticationRequest,
    SnowflakeAuthenticationResponse,
    SnowflakeAuthenticationStatusResponse,
)
from app.services.auth.snowflake_session_auth_service import (
    SnowflakeSessionAuthService,
)
from app.services.auth.snowflake_session_store import SNOWFLAKE_SESSION_COOKIE

router = APIRouter(dependencies=[Depends(require_lineage_api_key)])


@router.post(
    "/session",
    response_model=SnowflakeAuthenticationResponse,
)
async def authenticate_snowflake(
    request: SnowflakeAuthenticationRequest,
    response: Response,
    previous_session_id: str | None = Cookie(
        default=None,
        alias=SNOWFLAKE_SESSION_COOKIE,
    ),
) -> SnowflakeAuthenticationResponse:
    settings = get_settings()
    service = SnowflakeSessionAuthService()
    result = await asyncio.to_thread(
        service.authenticate,
        request,
    )
    if previous_session_id and previous_session_id != result.session_id:
        await asyncio.to_thread(service.logout, previous_session_id)
    response.set_cookie(
        key=SNOWFLAKE_SESSION_COOKIE,
        value=result.session_id,
        max_age=settings.snowflake_session_max_age_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
    return result


@router.get(
    "/session/status",
    response_model=SnowflakeAuthenticationStatusResponse,
)
async def snowflake_authentication_status(
    session_id: str | None = Cookie(
        default=None,
        alias=SNOWFLAKE_SESSION_COOKIE,
    ),
) -> SnowflakeAuthenticationStatusResponse:
    if session_id is None:
        raise ProviderAuthenticationRequiredError("snowflake")
    return await asyncio.to_thread(
        SnowflakeSessionAuthService().status,
        session_id,
    )


@router.delete("/session")
async def logout_snowflake(
    response: Response,
    session_id: str | None = Cookie(
        default=None,
        alias=SNOWFLAKE_SESSION_COOKIE,
    ),
) -> dict[str, str]:
    settings = get_settings()
    if session_id is not None:
        await asyncio.to_thread(
            SnowflakeSessionAuthService().logout,
            session_id,
        )
    response.delete_cookie(
        key=SNOWFLAKE_SESSION_COOKIE,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )
    return {"status": "logged_out"}
