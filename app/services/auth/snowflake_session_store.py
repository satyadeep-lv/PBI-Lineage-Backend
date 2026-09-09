from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from time import time
from typing import Any, Protocol
from uuid import uuid4

from app.schemas.snowflake_auth import SnowflakeAuthenticationMethod

SNOWFLAKE_SESSION_COOKIE = "pbi_lineage_snowflake_session"


class SnowflakeConnection(Protocol):
    def cursor(self) -> Any: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class SnowflakeSessionIdentity:
    authentication_method: SnowflakeAuthenticationMethod
    account_identifier: str
    user: str
    current_account: str | None = None
    current_user: str | None = None
    current_role: str | None = None
    current_warehouse: str | None = None
    current_database: str | None = None
    current_schema: str | None = None


@dataclass
class SnowflakeSession:
    session_id: str
    connection: SnowflakeConnection
    identity: SnowflakeSessionIdentity
    created_at: float
    expires_at: float
    active_operations: int = 0
    close_when_idle: bool = False


class SnowflakeSessionStore:
    def __init__(
        self,
        *,
        max_age_seconds: int,
        clock=time,
    ) -> None:
        self.max_age_seconds = max_age_seconds
        self.clock = clock
        self._sessions: dict[str, SnowflakeSession] = {}
        self._lock = RLock()

    def save(
        self,
        connection: SnowflakeConnection,
        identity: SnowflakeSessionIdentity,
    ) -> SnowflakeSession:
        now = self.clock()
        session = SnowflakeSession(
            session_id=str(uuid4()),
            connection=connection,
            identity=identity,
            created_at=now,
            expires_at=now + self.max_age_seconds,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> SnowflakeSession | None:
        connection_to_close = None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expires_at <= self.clock():
                self._sessions.pop(session_id, None)
                if session.active_operations:
                    session.close_when_idle = True
                else:
                    connection_to_close = session.connection
                session = None
        if connection_to_close is not None:
            self._close(connection_to_close)
        return session

    @contextmanager
    def checkout(self, session_id: str) -> Iterator[SnowflakeSession]:
        connection_to_close = None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.expires_at <= self.clock():
                self._sessions.pop(session_id, None)
                if session.active_operations:
                    session.close_when_idle = True
                else:
                    connection_to_close = session.connection
                session = None
            if session is not None:
                session.active_operations += 1

        if connection_to_close is not None:
            self._close(connection_to_close)
        if session is None:
            raise KeyError(session_id)

        try:
            yield session
        finally:
            connection_to_close = None
            with self._lock:
                session.active_operations = max(0, session.active_operations - 1)
                if session.close_when_idle and session.active_operations == 0:
                    connection_to_close = session.connection
            if connection_to_close is not None:
                self._close(connection_to_close)

    def delete(self, session_id: str) -> bool:
        connection_to_close = None
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return False
            if session.active_operations:
                session.close_when_idle = True
            else:
                connection_to_close = session.connection
        if connection_to_close is not None:
            self._close(connection_to_close)
        return True

    def remaining_seconds(self, session: SnowflakeSession) -> int:
        return max(0, int(session.expires_at - self.clock()))

    def close_all(self) -> None:
        connections_to_close: list[SnowflakeConnection] = []
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            for session in sessions:
                if session.active_operations:
                    session.close_when_idle = True
                else:
                    connections_to_close.append(session.connection)
        for connection in connections_to_close:
            self._close(connection)

    @staticmethod
    def _close(connection: SnowflakeConnection) -> None:
        try:
            connection.close()
        except Exception:  # noqa: BLE001 - connection cleanup boundary
            return


_snowflake_session_store: SnowflakeSessionStore | None = None
_snowflake_session_store_lock = RLock()


def get_snowflake_session_store(max_age_seconds: int) -> SnowflakeSessionStore:
    global _snowflake_session_store
    previous_store = None
    with _snowflake_session_store_lock:
        if (
            _snowflake_session_store is None
            or _snowflake_session_store.max_age_seconds != max_age_seconds
        ):
            previous_store = _snowflake_session_store
            _snowflake_session_store = SnowflakeSessionStore(
                max_age_seconds=max_age_seconds
            )
        store = _snowflake_session_store
    if previous_store is not None:
        previous_store.close_all()
    return store


def close_snowflake_session_store() -> None:
    global _snowflake_session_store
    with _snowflake_session_store_lock:
        store = _snowflake_session_store
        _snowflake_session_store = None
    if store is not None:
        store.close_all()
