from typing import Annotated

from fastapi import Cookie, Depends
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from app.core.auth_session import (
    AUTH_SESSION_COOKIE,
)
from app.core.exceptions import (
    AuthenticationSessionExpiredError,
    AuthenticationSessionRequiredError,
    InvalidAccessTokenError,
    InvalidAuthenticationSchemeError,
    MissingAuthenticationCredentialsError,
    ProviderAuthenticationRequiredError,
)
from app.services.auth.device_auth_store import (
    get_device_session,
    get_fabric_token,
    get_powerbi_token,
)
from app.services.auth.snowflake_session_store import SNOWFLAKE_SESSION_COOKIE

bearer_scheme = HTTPBearer(
    auto_error=False,
)


async def get_bearer_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> str:
    if credentials is None:
        raise (MissingAuthenticationCredentialsError())

    if credentials.scheme.lower() != "bearer":
        raise (InvalidAuthenticationSchemeError())

    return credentials.credentials


async def get_powerbi_access_token(
    session_id: str | None = Cookie(
        default=None,
        alias=AUTH_SESSION_COOKIE,
    ),
) -> str:
    if not session_id:
        raise (MissingAuthenticationCredentialsError())

    session = get_device_session(session_id)

    if session is None:
        raise (MissingAuthenticationCredentialsError())

    if session.status == "pending":
        raise (MissingAuthenticationCredentialsError())

    token = get_powerbi_token(session_id)

    if token is None:
        raise InvalidAccessTokenError("powerbi")

    return token


async def get_fabric_access_token(
    session_id: str | None = Cookie(
        default=None,
        alias=AUTH_SESSION_COOKIE,
    ),
) -> str:
    if not session_id:
        raise (AuthenticationSessionRequiredError())

    session = get_device_session(session_id)

    if session is None:
        raise (AuthenticationSessionExpiredError())

    token = get_fabric_token(session_id)

    if token is None:
        raise ProviderAuthenticationRequiredError(provider="fabric")

    return token


async def get_optional_fabric_access_token(
    session_id: str | None = Cookie(
        default=None,
        alias=AUTH_SESSION_COOKIE,
    ),
) -> str | None:
    """Fabric token if the session has one, else None (never raises).

    Used where Fabric access materially improves what can be answered but
    a missing/partial Fabric session should degrade gracefully rather than
    reject the whole request (e.g. Power AI, which can still say
    "insufficient evidence" instead of a hard 401).
    """
    if not session_id:
        return None

    return get_fabric_token(session_id)


async def get_snowflake_session_id(
    session_id: str | None = Cookie(
        default=None,
        alias=SNOWFLAKE_SESSION_COOKIE,
    ),
) -> str:
    if not session_id:
        raise ProviderAuthenticationRequiredError(provider="snowflake")
    return session_id
