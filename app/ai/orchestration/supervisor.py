from app.ai.agents.impact_agent import ImpactAgent
from app.ai.agents.measure_agent import MeasureAgent
from app.ai.agents.report_agent import ReportAgent
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
            return EvidenceBundle(
                question=question,
                context=resolved_context,
                evidence=[],
                can_answer=False,
                status=AIAnswerStatus.OUT_OF_SCOPE,
                agent=None,
                missing_information=[_OUT_OF_SCOPE_MESSAGE],
            )

        return agent.gather_evidence(question, resolved_context)
