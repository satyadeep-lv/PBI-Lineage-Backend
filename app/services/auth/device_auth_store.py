from dataclasses import dataclass, field
from time import time
from typing import Any

SESSION_MAX_AGE_SECONDS = 45 * 60


@dataclass
class DeviceAuthSession:
    tenant_id: str
    client_id: str

    authentication_method: str = "device_code"

    flow: dict[str, Any] = field(default_factory=dict)

    fabric_flow: dict[str, Any] = field(default_factory=dict)

    created_at: float = field(default_factory=time)

    status: str = "pending"

    powerbi_access_token: str | None = None
    powerbi_token_expires_at: float | None = None

    fabric_access_token: str | None = None
    fabric_token_expires_at: float | None = None

    powerbi_connected: bool | None = None
    fabric_connected: bool | None = None

    fabric_error_code: str | None = None
    error_message: str | None = None

    powerbi_granted_scopes: list[str] = field(default_factory=list)
    fabric_granted_scopes: list[str] = field(default_factory=list)
    powerbi_error_code: str | None = None


_device_sessions: dict[
    str,
    DeviceAuthSession,
] = {}


def save_device_session(
    session_id: str,
    session: DeviceAuthSession,
) -> None:
    _device_sessions[session_id] = session


def get_device_session(
    session_id: str,
) -> DeviceAuthSession | None:
    session = _device_sessions.get(session_id)

    if session is None:
        return None

    if time() - session.created_at > SESSION_MAX_AGE_SECONDS:
        delete_device_session(session_id)

        return None

    return session


def get_powerbi_token(
    session_id: str,
) -> str | None:
    session = get_device_session(session_id)

    if session is None:
        return None

    token = session.powerbi_access_token

    if not token:
        return None

    expires_at = session.powerbi_token_expires_at

    if expires_at is not None and time() >= expires_at:
        session.powerbi_access_token = None
        session.powerbi_connected = False
        session.powerbi_granted_scopes.clear()
        session.powerbi_error_code = "token_expired"

        return None

    return token


def get_fabric_token(
    session_id: str,
) -> str | None:
    session = get_device_session(session_id)

    if session is None:
        return None

    token = session.fabric_access_token

    if not token:
        return None

    expires_at = session.fabric_token_expires_at

    if expires_at is not None and time() >= expires_at:
        session.fabric_access_token = None
        session.fabric_connected = False
        session.fabric_granted_scopes.clear()
        session.fabric_error_code = "token_expired"

        return None

    return token


def delete_device_session(
    session_id: str,
) -> None:
    session = _device_sessions.pop(session_id, None)

    if session is None:
        return

    session.powerbi_access_token = None
    session.fabric_access_token = None

    session.powerbi_granted_scopes.clear()
    session.fabric_granted_scopes.clear()

    session.powerbi_error_code = None
    session.fabric_error_code = None

    session.flow.clear()
    session.fabric_flow.clear()
