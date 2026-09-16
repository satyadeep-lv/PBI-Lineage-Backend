import logging
import time
import uuid

from app.ai.composition.deterministic_renderer import DeterministicAnswerRenderer
from app.ai.composition.grounded_composer import ComposerFailure, compose
from app.ai.composition.grounding_validator import (
    GroundedResponseValidator,
    GroundingRejectedError,
)
from app.ai.composition.suggested_questions import suggested_questions_for
from app.ai.context.resolver import AIContextResolver
from app.ai.models.enums import AIAnswerStatus, AudienceType
from app.ai.models.evidence import EvidenceBundle, GroundedClaim
from app.ai.models.requests import AIChatRequest
from app.ai.models.responses import AIChatResponse, AIStatusResponse, AIUsage
from app.ai.orchestration.intent import classify_intent
from app.ai.orchestration.supervisor import Supervisor
from app.ai.providers.base import ModelGateway
from app.ai.providers.factory import build_model_gateway, is_provider_configured
from app.core.config import Settings
from app.core.exceptions import AIDisabledError
from app.core.metrics import metrics_registry

logger = logging.getLogger("app.ai")

_STATUS_METRIC_BY_ANSWER_STATUS: dict[AIAnswerStatus, str] = {
    AIAnswerStatus.INSUFFICIENT_EVIDENCE: "ai_insufficient_evidence_total",
    AIAnswerStatus.CONFLICTING_EVIDENCE: "ai_conflicting_evidence_total",
}


class AIService:
    """Orchestrates one request end to end.

    resolver -> supervisor/agent -> evidence gate -> composer -> validator
    -> deterministic fallback. The model is only ever invoked once, and
    only when `EvidenceBundle.can_answer` is True.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        gateway: ModelGateway | None = None,
        powerbi_access_token: str | None = None,
        fabric_access_token: str | None = None,
    ) -> None:
        self._settings = settings
        self._gateway = gateway or build_model_gateway(settings)
        self._powerbi_access_token = powerbi_access_token
        self._fabric_access_token = fabric_access_token

    def status(self) -> AIStatusResponse:
        return AIStatusResponse(
            enabled=self._settings.ai_enabled,
            provider=self._settings.ai_provider,
            model=self._settings.ai_model,
            streaming_enabled=self._settings.ai_streaming_enabled,
            configured=is_provider_configured(self._settings),
        )

    async def build_evidence_bundle(
        self,
        request: AIChatRequest,
    ) -> EvidenceBundle:
        resolver = AIContextResolver(
            powerbi_access_token=self._powerbi_access_token,
            fabric_access_token=self._fabric_access_token,
        )
        resolved_context = await resolver.resolve(request.context)

        return Supervisor().handle(
            question=request.message,
            chat_context=request.context,
            resolved_context=resolved_context,
        )

    async def generate(
        self,
        request: AIChatRequest,
    ) -> AIChatResponse:
        if not self._settings.ai_enabled:
            raise AIDisabledError()

        conversation_id = request.conversation_id or str(uuid.uuid4())
        metrics_registry.record_grounding_event("ai_requests_total")

        bundle = await self.build_evidence_bundle(request)

        logger.info(
            "ai_evidence_gathered",
            extra={
                "event": "ai_evidence_gathered",
                "conversation_id": conversation_id,
                "intent": classify_intent(request.message, request.context).value,
                "agent": bundle.agent,
                "evidence_count": len(bundle.evidence),
                "evidence_status": bundle.status.value,
            },
        )

        if not bundle.can_answer:
            metric_name = _STATUS_METRIC_BY_ANSWER_STATUS.get(bundle.status)
            if metric_name:
                metrics_registry.record_grounding_event(metric_name)

            # The core rule: no verified evidence -> no factual answer, and
            # the model is never called to guess. This branch covers
            # insufficient_evidence, ambiguous, conflicting_evidence, and
            # out_of_scope alike.
            return AIChatResponse(
                conversation_id=conversation_id,
                status=bundle.status,
                answer=DeterministicAnswerRenderer.render(bundle, request.audience),
                claims=[],
                evidence=bundle.evidence,
                agent=bundle.agent,
                suggested_questions=suggested_questions_for(request.context),
                usage=None,
            )

        answer, claims, usage, fallback_used = await self._compose_grounded_answer(
            bundle,
            audience=request.audience,
        )

        metrics_registry.record_grounding_event(
            "ai_deterministic_fallback_total"
            if fallback_used
            else "ai_grounded_answers_total"
        )

        logger.info(
            "ai_generate_completed",
            extra={
                "event": "ai_generate_completed",
                "conversation_id": conversation_id,
                "agent": bundle.agent,
                "evidence_count": len(bundle.evidence),
                "evidence_status": bundle.status.value,
                "validation_result": "fallback" if fallback_used else "passed",
                "fallback_used": fallback_used,
            },
        )

        return AIChatResponse(
            conversation_id=conversation_id,
            status=AIAnswerStatus.ANSWERED,
            answer=answer,
            claims=claims,
            evidence=bundle.evidence,
            agent=bundle.agent,
            suggested_questions=suggested_questions_for(request.context),
            usage=usage,
        )

    async def _compose_grounded_answer(
        self,
        bundle: EvidenceBundle,
        *,
        audience: AudienceType,
    ) -> tuple[str, list[GroundedClaim], AIUsage | None, bool]:
        started_at = time.monotonic()

        try:
            composed, model_response = await compose(
                self._gateway,
                bundle,
                audience=audience,
                temperature=self._settings.ai_temperature,
            )
            claims = GroundedResponseValidator.validate(composed.claims, bundle)
            usage = AIUsage(
                provider=model_response.provider,
                model=model_response.model,
                tokens=model_response.usage.total_tokens,
            )
            return composed.summary, claims, usage, False
        except GroundingRejectedError:
            metrics_registry.record_grounding_event(
                "ai_grounding_validation_failed_total"
            )
        except ComposerFailure:
            metrics_registry.record_grounding_event("ai_provider_failure_total")
        except Exception:
            # Any other provider/composition failure still must not prevent
            # a factual answer when the evidence itself was sufficient.
            logger.warning(
                "ai_composition_failed",
                extra={"event": "ai_composition_failed"},
            )
            metrics_registry.record_grounding_event("ai_provider_failure_total")
        finally:
            duration_ms = round((time.monotonic() - started_at) * 1000, 2)
            logger.debug(
                "ai_compose_attempted",
                extra={"event": "ai_compose_attempted", "duration_ms": duration_ms},
            )

        return (
            DeterministicAnswerRenderer.render(bundle, audience),
            [],
            None,
            True,
        )
