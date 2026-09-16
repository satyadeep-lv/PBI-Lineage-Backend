import json
from collections.abc import AsyncIterator

from app.ai.models.requests import AIChatRequest
from app.ai.services.ai_service import AIService
from app.core.exceptions import AppException

_CHUNK_TARGET_LENGTH = 40


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _chunk_text(text: str, *, target_length: int = _CHUNK_TARGET_LENGTH) -> list[str]:
    if not text:
        return []

    words = text.split(" ")
    chunks: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip() if current else word

        if current and len(candidate) > target_length:
            chunks.append(current)
            current = word
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


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
    """
    try:
        response = await service.generate(request)
    except AppException as exc:
        yield _sse_event("error", {"code": exc.code, "message": exc.message})
        return
    except Exception as exc:  # noqa: BLE001 - last-resort stream safety net
        yield _sse_event(
            "error",
            {"code": "AI_STREAM_ERROR", "message": str(exc)},
        )
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
        yield _sse_event("delta", {"delta": chunk})

    # No duplicate final message: `complete` carries metadata/claims/usage
    # only — the answer text itself was already fully delivered via delta
    # events above.
    yield _sse_event(
        "complete",
        {
            "conversation_id": response.conversation_id,
            "status": response.status.value,
            "claims": [claim.model_dump(mode="json") for claim in response.claims],
            "suggested_questions": response.suggested_questions,
            "usage": (
                response.usage.model_dump(mode="json") if response.usage else None
            ),
        },
    )
