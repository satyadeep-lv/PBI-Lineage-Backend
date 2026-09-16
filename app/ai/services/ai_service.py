import logging
import time

from app.ai.models.enums import MessageRole
from app.ai.models.messages import ModelMessage
from app.ai.models.requests import AIChatRequest, ModelRequest
from app.ai.models.responses import AIChatResponse, AIStatusResponse, AIUsage
from app.ai.providers.base import ModelGateway
from app.ai.providers.factory import build_model_gateway, is_provider_configured
from app.core.config import Settings
from app.core.exceptions import AIDisabledError

logger = logging.getLogger("app.ai")

_SYSTEM_PROMPT = (
    "You are Power AI, an assistant that explains Power BI/Fabric/Snowflake "
    "lineage evidence already computed by this backend's deterministic "
    "lineage engine. Only use information given to you. If evidence is "
    "missing or was not supplied, say so plainly instead of guessing."
)


class AIService:
    def __init__(
        self,
        *,
        settings: Settings,
        gateway: ModelGateway | None = None,
    ) -> None:
        self._settings = settings
        self._gateway = gateway or build_model_gateway(settings)

    def status(self) -> AIStatusResponse:
        return AIStatusResponse(
            enabled=self._settings.ai_enabled,
            provider=self._settings.ai_provider,
            model=self._settings.ai_model,
            streaming_enabled=self._settings.ai_streaming_enabled,
            configured=is_provider_configured(self._settings),
        )

    async def generate(
        self,
        request: AIChatRequest,
    ) -> AIChatResponse:
        if not self._settings.ai_enabled:
            raise AIDisabledError()

        model_request = ModelRequest(
            messages=[
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content=_SYSTEM_PROMPT,
                ),
                ModelMessage(
                    role=MessageRole.USER,
                    content=request.message,
                ),
            ],
        )

        started_at = time.monotonic()

        try:
            model_response = await self._gateway.generate(model_request)
        except Exception as exc:
            logger.warning(
                "ai_generate_failed",
                extra={
                    "event": "ai_generate_failed",
                    "provider": self._settings.ai_provider,
                    "model": self._settings.ai_model,
                    "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                    "error_code": getattr(exc, "code", type(exc).__name__),
                },
            )
            raise

        logger.info(
            "ai_generate_completed",
            extra={
                "event": "ai_generate_completed",
                "provider": model_response.provider,
                "model": model_response.model,
                "tokens": model_response.usage.total_tokens,
                "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
            },
        )

        return AIChatResponse(
            conversation_id=request.conversation_id,
            answer=model_response.content,
            agent=None,
            evidence=[],
            suggested_questions=[],
            usage=AIUsage(
                provider=model_response.provider,
                model=model_response.model,
                tokens=model_response.usage.total_tokens,
            ),
        )
