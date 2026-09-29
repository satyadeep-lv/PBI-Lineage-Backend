from app.ai.agents.base import build_bundle
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceBundle
from app.ai.tools import dossier_tools

NAME = "impact_agent"


class ImpactAgent:
    name = NAME

    def gather_evidence(
        self,
        question: str,
        context: ResolvedAIContext,
    ) -> EvidenceBundle:
        resolved = context.resolved_object

        if resolved is None:
            return build_bundle(
                question=question,
                context=context,
                agent=NAME,
                evidence=[],
                status=(
                    AIAnswerStatus.AMBIGUOUS
                    if context.resolution_notes
                    else AIAnswerStatus.INSUFFICIENT_EVIDENCE
                ),
                missing_information=context.resolution_notes
                or [
                    "Could not resolve the object referenced in this "
                    "question from the available lineage evidence."
                ],
            )

        evidence = dossier_tools.object_dossier(context)
        lineage = [
            item
            for item in evidence
            if item.fact_type in ("dependency", "source", "impact")
        ]

        if not lineage:
            return build_bundle(
                question=question,
                context=context,
                agent=NAME,
                evidence=[],
                status=AIAnswerStatus.INSUFFICIENT_EVIDENCE,
                missing_information=[
                    "No upstream or downstream lineage evidence was found "
                    f"for {resolved.qualified_name}."
                ],
            )

        return build_bundle(
            question=question,
            context=context,
            agent=NAME,
            evidence=evidence,
            status=AIAnswerStatus.ANSWERED,
        )
