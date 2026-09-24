from app.ai.agents.base import build_bundle
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceBundle
from app.ai.tools import dossier_tools, report_tools

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

        # The report dossier answers "what is it, which model powers it,
        # which measures does it use, where does its data come from"; the
        # per-visual field list is kept for "what does this chart show".
        evidence = [
            *dossier_tools.report_dossier(context),
            *report_tools.get_report_visuals(context),
        ]

        return build_bundle(
            question=question,
            context=context,
            agent=NAME,
            evidence=evidence,
            status=AIAnswerStatus.ANSWERED,
        )
