from app.clients.snowflake_session_client import SnowflakeSessionClient
from app.core.config import Settings, get_settings
from app.core.exceptions import ProviderAuthenticationRequiredError
from app.schemas.snowflake_auth import (
    SnowflakeAuthenticationRequest,
    SnowflakeAuthenticationResponse,
    SnowflakeAuthenticationStatusResponse,
)
from app.services.auth.snowflake_session_store import (
    SnowflakeSession,
    SnowflakeSessionStore,
    get_snowflake_session_store,
)


class SnowflakeSessionAuthService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: SnowflakeSessionClient | None = None,
        store: SnowflakeSessionStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or SnowflakeSessionClient(
            allow_external_browser=(self.settings.snowflake_allow_external_browser_auth)
        )
        self.store = store or get_snowflake_session_store(
            self.settings.snowflake_session_max_age_seconds
        )

    def authenticate(
        self,
        request: SnowflakeAuthenticationRequest,
    ) -> SnowflakeAuthenticationResponse:
        connection, identity = self.client.connect(request)
        session = self.store.save(connection, identity)
        return self._authentication_response(session)

    def status(self, session_id: str) -> SnowflakeAuthenticationStatusResponse:
        session = self.store.get(session_id)
        if session is None:
            raise ProviderAuthenticationRequiredError("snowflake")
        identity = session.identity
        return SnowflakeAuthenticationStatusResponse(
            **identity.__dict__,
            expires_in=self.store.remaining_seconds(session),
        )

    def logout(self, session_id: str) -> None:
        self.store.delete(session_id)

    def _authentication_response(
        self,
        session: SnowflakeSession,
    ) -> SnowflakeAuthenticationResponse:
        return SnowflakeAuthenticationResponse(
            session_id=session.session_id,
            **session.identity.__dict__,
            expires_in=self.store.remaining_seconds(session),
        )
