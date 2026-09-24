from app.ai.agents.base import build_bundle
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceBundle
from app.ai.tools import lineage_tools, report_tools

NAME = "semantic_model_agent"


class SemanticModelAgent:
    """Answers "what is here" rather than "explain this one object".

    `AIIntent.SEMANTIC_MODEL_INFORMATION` existed with no agent behind it, so
    every inventory or orientation question ("what measures are there", "how
    many reports", "what am I looking at") either fell through to an agent
    that needed a specific object resolved -- and reported insufficient
    evidence -- or fell out as out-of-scope. The model already knows all of
    this; nothing here needs resolving first.
    """

    name = NAME

    def gather_evidence(
        self,
        question: str,
        context: ResolvedAIContext,
    ) -> EvidenceBundle:
        evidence = [
            *lineage_tools.get_semantic_model_details(context),
            *report_tools.get_report_summary(context),
            *report_tools.get_report_pages(context),
            *lineage_tools.get_physical_sources(context),
        ]

        if not evidence:
            return build_bundle(
                question=question,
                context=context,
                agent=NAME,
                evidence=[],
                status=AIAnswerStatus.INSUFFICIENT_EVIDENCE,
                missing_information=context.resolution_notes
                or [
                    "No semantic model or report is in context yet. Open a "
                    "report or semantic model and ask again."
                ],
            )

        return build_bundle(
            question=question,
            context=context,
            agent=NAME,
            evidence=evidence,
            status=AIAnswerStatus.ANSWERED,
        )
