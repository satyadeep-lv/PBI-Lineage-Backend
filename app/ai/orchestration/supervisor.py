from app.ai.agents.impact_agent import ImpactAgent
from app.ai.agents.measure_agent import MeasureAgent
from app.ai.agents.report_agent import ReportAgent
from app.ai.agents.semantic_model_agent import SemanticModelAgent
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus, AIIntent
from app.ai.models.evidence import EvidenceBundle
from app.ai.models.requests import AIChatContext
from app.ai.orchestration.intent import classify_intent

_AGENTS_BY_INTENT = {
    AIIntent.MEASURE_EXPLANATION: MeasureAgent(),
    AIIntent.CALCULATED_COLUMN_EXPLANATION: MeasureAgent(),
    AIIntent.OBJECT_IMPACT: ImpactAgent(),
    AIIntent.REPORT_INFORMATION: ReportAgent(),
    AIIntent.SEMANTIC_MODEL_INFORMATION: SemanticModelAgent(),
}

_OUT_OF_SCOPE_MESSAGE = (
    "This question is outside Power AI's current scope. Try asking about a "
    "specific measure, report, or the impact of a specific object."
)


class Supervisor:
    """Determines intent, inspects resolved context, chooses one agent.

    Never manufactures facts itself — its only job is routing. Evidence
    gathering, and the decision of whether there is enough evidence to
    answer, belong entirely to the chosen agent.
    """

    def handle(
        self,
        *,
        question: str,
        chat_context: AIChatContext | None,
        resolved_context: ResolvedAIContext,
    ) -> EvidenceBundle:
        intent = classify_intent(question, chat_context)
        agent = _AGENTS_BY_INTENT.get(intent)

        if agent is None:
            return self._fallback(
                question=question,
                resolved_context=resolved_context,
                status=AIAnswerStatus.OUT_OF_SCOPE,
                note=_OUT_OF_SCOPE_MESSAGE,
            )

        bundle = agent.gather_evidence(question, resolved_context)

        if bundle.can_answer or isinstance(agent, SemanticModelAgent):
            return bundle

        # The chosen agent could not resolve the specific object asked about.
        # Rather than stopping at "insufficient evidence", say what *is*
        # known about the model in view -- a dead end is never the most
        # useful true answer available.
        return self._fallback(
            question=question,
            resolved_context=resolved_context,
            status=bundle.status,
            note=(bundle.missing_information or [_OUT_OF_SCOPE_MESSAGE])[0],
            original=bundle,
        )

    @staticmethod
    def _fallback(
        *,
        question: str,
        resolved_context: ResolvedAIContext,
        status: AIAnswerStatus,
        note: str,
        original: EvidenceBundle | None = None,
    ) -> EvidenceBundle:
        overview = SemanticModelAgent().gather_evidence(question, resolved_context)

        if not overview.can_answer:
            if original is not None:
                return original
            return EvidenceBundle(
                question=question,
                context=resolved_context,
                evidence=[],
                can_answer=False,
                status=status,
                agent=None,
                missing_information=[note],
            )

        return overview.model_copy(
            update={"missing_information": [note, *overview.missing_information]}
        )
