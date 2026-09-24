"""Recent turns of each Power AI conversation, so follow-ups make sense.

Every request used to reach the model as a lone question, so "which visuals
use it?" after "explain Total Revenue" had nothing for "it" to refer to. The
frontend already sends a `conversation_id`; this keeps the last few turns
behind it.

Keyed by a fingerprint of the caller's access token as well as the id -- the
same principal-scoping the provider read cache uses -- so a conversation id
that leaks or is guessed never replays another user's questions. Process-
local and bounded, like the rest of this single-worker deployment's session
state; losing it on restart only costs follow-up context, never an answer.
"""

from app.services.provider_read_cache import ProviderReadCache
from app.services.ttl_cache import TTLCache

MAX_TURNS = 10
_TTL_SECONDS = 2 * 60 * 60
_MAX_CONVERSATIONS = 1000

Turn = tuple[str, str]

_turns: TTLCache[tuple[str, str], tuple[Turn, ...]] = TTLCache(
    ttl_seconds=_TTL_SECONDS,
    max_entries=_MAX_CONVERSATIONS,
)


def _key(access_token: str, conversation_id: str) -> tuple[str, str]:
    return (ProviderReadCache.fingerprint(access_token), conversation_id)


def conversation_history(
    access_token: str | None,
    conversation_id: str | None,
) -> list[Turn]:
    if not access_token or not conversation_id:
        return []
    return list(_turns.get(_key(access_token, conversation_id)) or ())


def remember_turn(
    access_token: str | None,
    conversation_id: str,
    question: str,
    answer: str,
) -> None:
    if not access_token or not answer:
        return
    key = _key(access_token, conversation_id)
    turns = (*(_turns.get(key) or ()), (question, answer))
    _turns.set(key, turns[-MAX_TURNS:])


def reset_conversation_store() -> None:
    _turns.invalidate()
