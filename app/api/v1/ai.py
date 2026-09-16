from fastapi import APIRouter, Depends

from app.ai.models.requests import AIChatRequest
from app.ai.models.responses import AIChatResponse, AIStatusResponse
from app.ai.services.ai_service import AIService
from app.api.dependencies.credentials import get_powerbi_access_token
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
    "/chat",
    response_model=AIChatResponse,
    dependencies=[Depends(get_powerbi_access_token)],
)
async def post_ai_chat(
    request: AIChatRequest,
) -> AIChatResponse:
    return await AIService(settings=get_settings()).generate(request)
