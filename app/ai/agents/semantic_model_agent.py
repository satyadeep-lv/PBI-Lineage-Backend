from app.ai.agents.base import build_bundle
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceBundle
from app.ai.tools import dossier_tools

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
        # With a report open, "what am I looking at" is first about that
        # report; the model behind it follows.
        evidence = [
            *dossier_tools.report_dossier(context),
            *dossier_tools.model_dossier(context),
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
            evidence=_without_repeated_coverage(evidence),
            status=AIAnswerStatus.ANSWERED,
        )


def _without_repeated_coverage(evidence):
    """Both dossiers restate the context's coverage notes; keep one copy."""
    seen: set[str] = set()
    kept = []
    for item in evidence:
        if item.object_type == "coverage":
            if item.display_value in seen:
                continue
            seen.add(item.display_value or "")
        kept.append(item)
    return kept
