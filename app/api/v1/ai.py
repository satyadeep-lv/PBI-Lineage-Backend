from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.ai.models.requests import AIChatRequest
from app.ai.models.responses import AIChatResponse, AIStatusResponse
from app.ai.services.ai_service import AIService
from app.ai.services.streaming import stream_chat_response
from app.api.dependencies.credentials import (
    get_optional_fabric_access_token,
    get_powerbi_access_token,
)
from app.api.dependencies.security import require_lineage_api_key
from app.core.config import get_settings

router = APIRouter(dependencies=[Depends(require_lineage_api_key)])


@router.get(
    "/status",
    response_model=AIStatusResponse,
    dependencies=[Depends(get_powerbi_access_token)],
)
async def get_ai_status() -> AIStatusResponse:
    return AIService(settings=get_settings()).status()


@router.post(
    "/explain",
    response_model=AIChatResponse,
)
async def post_ai_explain(
    request: AIChatRequest,
    powerbi_access_token: str = Depends(get_powerbi_access_token),
    fabric_access_token: str | None = Depends(get_optional_fabric_access_token),
) -> AIChatResponse:
    """Evidence-first answer that works with AI disabled.

    Same request and response shape as `/chat`. The facts are gathered
    deterministically; when AI is enabled and configured a model writes them
    up (one call, no tools, claims checked against the evidence), and
    otherwise -- or if that fails -- the answer is rendered straight from the
    evidence, so it cannot be blocked by provider configuration or
    reachability. `usage` says whether a model was involved.
    """
    service = AIService(
        settings=get_settings(),
        powerbi_access_token=powerbi_access_token,
        fabric_access_token=fabric_access_token,
    )
    return await service.explain(request)


@router.post(
    "/chat",
    response_model=AIChatResponse,
)
async def post_ai_chat(
    request: AIChatRequest,
    powerbi_access_token: str = Depends(get_powerbi_access_token),
    fabric_access_token: str | None = Depends(get_optional_fabric_access_token),
) -> AIChatResponse:
    service = AIService(
        settings=get_settings(),
        powerbi_access_token=powerbi_access_token,
        fabric_access_token=fabric_access_token,
    )
    return await service.generate(request)


@router.post(
    "/chat/stream",
)
async def post_ai_chat_stream(
    request: AIChatRequest,
    powerbi_access_token: str = Depends(get_powerbi_access_token),
    fabric_access_token: str | None = Depends(get_optional_fabric_access_token),
) -> StreamingResponse:
    service = AIService(
        settings=get_settings(),
        powerbi_access_token=powerbi_access_token,
        fabric_access_token=fabric_access_token,
    )
    return StreamingResponse(
        stream_chat_response(service, request),
        media_type="text/event-stream",
    )
