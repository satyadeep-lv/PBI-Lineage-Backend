from dataclasses import dataclass, field
from time import time

PENDING_SSO_LOGIN_MAX_AGE_SECONDS = 10 * 60


@dataclass
class PendingSsoLogin:
    tenant_id: str
    client_id: str
    code_verifier: str
    redirect_uri: str
    post_login_redirect_uri: str | None

    created_at: float = field(default_factory=time)


_pending_logins: dict[str, PendingSsoLogin] = {}


def save_pending_sso_login(
    state: str,
    login: PendingSsoLogin,
) -> None:
    _pending_logins[state] = login


def pop_pending_sso_login(
    state: str,
) -> PendingSsoLogin | None:
    login = _pending_logins.pop(state, None)

    if login is None:
        return None

    if time() - login.created_at > PENDING_SSO_LOGIN_MAX_AGE_SECONDS:
        return None

    return login
