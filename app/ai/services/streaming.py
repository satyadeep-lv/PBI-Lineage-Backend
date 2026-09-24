import json
import re
from collections.abc import AsyncIterator

from app.ai.models.requests import AIChatRequest
from app.ai.services.ai_service import AIService
from app.core.exceptions import AppException

_CHUNK_TARGET_LENGTH = 40

# A word plus the whitespace after it, so chunks concatenate back to the exact
# answer -- newlines and DAX indentation included.
_TOKEN = re.compile(r"\S+\s*|\s+")

# The frontend picks its (vetted) error copy from `reason`; these are the
# reasons it knows. Anything unmapped falls back to its generic message.
_REASON_BY_CODE = {
    "AI_DISABLED": "disabled",
    "AI_PROVIDER_UNAVAILABLE": "provider_unavailable",
    "AI_PROVIDER_ERROR": "provider_unavailable",
    "AI_PROVIDER_AUTH_FAILED": "not_configured",
    "AI_PROVIDER_TIMEOUT": "timeout",
    "AI_PROVIDER_RATE_LIMITED": "rate_limited",
    "UPSTREAM_TIMEOUT": "timeout",
    "UPSTREAM_RATE_LIMITED": "rate_limited",
    "UPSTREAM_SERVICE_UNAVAILABLE": "provider_unavailable",
    "AUTH_INSUFFICIENT_PERMISSIONS": "insufficient_permissions",
}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _chunk_text(text: str, *, target_length: int = _CHUNK_TARGET_LENGTH) -> list[str]:
    """Split an answer into small pieces that join back to it exactly.

    The previous split on single spaces dropped the space between chunks,
    so a client appending deltas received "Explain thisreport".
    """
    if not text:
        return []

    chunks: list[str] = []
    current = ""

    for token in _TOKEN.findall(text):
        if current and len(current) + len(token.rstrip()) > target_length:
            chunks.append(current)
            current = ""
        current += token

    if current:
        chunks.append(current)

    return chunks


def _error_event(code: str, message: str) -> str:
    reason = _REASON_BY_CODE.get(code)
    if reason is None and code.startswith("AUTH_"):
        reason = "auth_required"
    return _sse_event(
        "error",
        {
            "code": code,
            "message": message,
            # The frontend reads `error` and `reason`; `code`/`message` are
            # kept for any other consumer of this stream.
            "error": message,
            "reason": reason or "unknown",
        },
    )


async def stream_chat_response(
    service: AIService,
    request: AIChatRequest,
) -> AsyncIterator[str]:
    """Ground fully, THEN stream — never speculative token-level output.

    The entire resolver -> supervisor -> evidence-gate -> composer ->
    validator pipeline runs to a single, already-validated AIChatResponse
    before any byte is emitted. Streaming only chunks the delivery of that
    already-grounded answer; it never streams unsupported claims that get
    retracted later.

    Event contract (what the frontend's `streamChatMessage` parses):
      metadata -> {conversation_id, status, agent}
      evidence -> {evidence: [...]}
      delta    -> {text, delta}: the next piece of the answer
      complete -> the full AIChatResponse. It is authoritative: the client
                  replaces the text it accumulated from deltas with
                  `answer`, so nothing is duplicated -- and nothing is lost
                  if a delta was dropped.
      error    -> {code, message, error, reason}
    """
    try:
        response = await service.generate(request)
    except AppException as exc:
        yield _error_event(exc.code, exc.message)
        return
    except Exception as exc:  # noqa: BLE001 - last-resort stream safety net
        yield _error_event("AI_STREAM_ERROR", str(exc))
        return

    yield _sse_event(
        "metadata",
        {
            "conversation_id": response.conversation_id,
            "status": response.status.value,
            "agent": response.agent,
        },
    )

    yield _sse_event(
        "evidence",
        {"evidence": [item.model_dump(mode="json") for item in response.evidence]},
    )

    for chunk in _chunk_text(response.answer):
        yield _sse_event("delta", {"text": chunk, "delta": chunk})

    # `complete` used to carry metadata only, on the theory that the answer
    # had already arrived as deltas. The frontend treats `complete` as the
    # final response and sets the message text to its `answer` -- which was
    # absent, so every streamed answer ended as an empty bubble.
    yield _sse_event("complete", response.model_dump(mode="json"))
