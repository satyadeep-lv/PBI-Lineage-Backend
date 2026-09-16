from app.ai.agents.base import build_bundle
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceBundle
from app.ai.tools import lineage_tools, report_tools

NAME = "report_agent"


class ReportAgent:
    name = NAME

    def gather_evidence(
        self,
        question: str,
        context: ResolvedAIContext,
    ) -> EvidenceBundle:
        if context.report_definition is None:
            return build_bundle(
                question=question,
                context=context,
                agent=NAME,
                evidence=[],
                status=AIAnswerStatus.INSUFFICIENT_EVIDENCE,
                missing_information=context.resolution_notes
                or ["Could not resolve the requested report."],
            )

        evidence = [
            *report_tools.get_report_summary(context),
            *report_tools.get_report_pages(context),
            *report_tools.get_report_visuals(context),
            *lineage_tools.get_semantic_model_details(context),
            *lineage_tools.get_physical_sources(context),
        ]

        return build_bundle(
            question=question,
            context=context,
            agent=NAME,
            evidence=evidence,
            status=AIAnswerStatus.ANSWERED,
        )
