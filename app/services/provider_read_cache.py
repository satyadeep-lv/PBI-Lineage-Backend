"""Session-scoped cache for repeated provider reads.

Browsing the app re-asks Power BI and Fabric for the same workspaces, reports
and definitions on every screen. Those reads are idempotent and change rarely
within a sitting, so they are cached per signed-in session.

Entries are keyed by a fingerprint of the caller's access token, never shared
between principals: two users can have very different access to the same
object, so a cached answer is only ever replayed to the token that fetched it.
Because a session's token does not rotate silently -- it expires and the user
re-authenticates -- that fingerprint is stable for the life of a session,
which is what makes this a session cache without having to thread a session ID
through every endpoint.

Only successful reads are cached. A failure is never remembered, so a
permission that has just been granted takes effect on the next attempt.
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings
from app.services.ttl_cache import TTLCache

CacheKey = tuple[str, ...]


class ProviderReadCache:
    def __init__(self, *, ttl_seconds: float, max_entries: int) -> None:
        self._entries: TTLCache[CacheKey, Any] = TTLCache(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
        )
        self._fetches: dict[CacheKey, asyncio.Future[Any]] = {}
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    @staticmethod
    def fingerprint(access_token: str) -> str:
        return hashlib.sha256(access_token.encode("utf-8")).hexdigest()

    async def get_or_fetch(
        self,
        key: CacheKey,
        factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        if not self.enabled:
            return await factory()

        cached = self._entries.get(key)
        if cached is not None:
            return cached

        in_flight = self._fetches.get(key)
        if in_flight is not None:
            # Several screens can open at once and ask for the same thing;
            # they wait on one request rather than starting their own.
            return await asyncio.shield(in_flight)

        fetch: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._fetches[key] = fetch

        try:
            value = await factory()
        except BaseException as error:
            if not fetch.done():
                fetch.set_exception(error)
            # Nobody will await a failed future; reading it keeps asyncio from
            # logging "exception was never retrieved".
            fetch.exception()
            raise
        else:
            if not fetch.done():
                fetch.set_result(value)
            self._entries.set(key, value)
            return value
        finally:
            self._fetches.pop(key, None)

    def invalidate_session(self, access_token: str) -> None:
        session = self.fingerprint(access_token)
        self._entries.invalidate(lambda key: bool(key) and key[0] == session)

    def clear(self) -> None:
        self._entries.invalidate()

    def __len__(self) -> int:
        return len(self._entries)


_cache: ProviderReadCache | None = None


def get_provider_read_cache() -> ProviderReadCache:
    global _cache

    if _cache is None:
        settings = get_settings()
        _cache = ProviderReadCache(
            ttl_seconds=settings.provider_read_cache_ttl_seconds,
            max_entries=settings.provider_read_cache_max_entries,
        )

    return _cache


def reset_provider_read_cache() -> None:
    global _cache

    _cache = None
