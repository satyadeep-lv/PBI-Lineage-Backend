from app.ai.agents.base import build_bundle
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceBundle
from app.ai.tools import impact_tools, lineage_tools, measure_tools

NAME = "measure_agent"


class MeasureAgent:
    name = NAME

    def gather_evidence(
        self,
        question: str,
        context: ResolvedAIContext,
    ) -> EvidenceBundle:
        resolved = context.resolved_object

        if resolved is None or resolved.object_type not in (
            "measure",
            "calculated_column",
        ):
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
                    "Could not resolve the requested measure or calculated "
                    "column from the available lineage evidence."
                ],
            )

        if resolved.object_type == "measure":
            definition = measure_tools.get_measure_definition(context)
        else:
            definition = measure_tools.get_calculated_column_definition(context)

        if not definition:
            return build_bundle(
                question=question,
                context=context,
                agent=NAME,
                evidence=[],
                status=AIAnswerStatus.INSUFFICIENT_EVIDENCE,
                missing_information=[
                    f"No DAX definition was found for {resolved.qualified_name} "
                    "in the currently available lineage evidence."
                ],
            )

        # Physical sources/dependencies reachable upstream of this specific
        # object, and its downstream impact with distance — bounded-depth,
        # not the entire enterprise graph.
        upstream = lineage_tools.get_upstream_lineage(context)
        impact = impact_tools.analyze_impact(context)

        conflict = None
        if resolved.object_type == "measure":
            conflict = measure_tools.detect_measure_conflict(context)

        evidence = [*definition, *upstream, *impact]

        if conflict is not None:
            return build_bundle(
                question=question,
                context=context,
                agent=NAME,
                evidence=evidence,
                status=AIAnswerStatus.CONFLICTING_EVIDENCE,
                conflicts=[conflict],
            )

        return build_bundle(
            question=question,
            context=context,
            agent=NAME,
            evidence=evidence,
            status=AIAnswerStatus.ANSWERED,
        )
