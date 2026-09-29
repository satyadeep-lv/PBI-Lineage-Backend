from app.ai.agents.base import build_bundle
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceBundle
from app.ai.tools import dossier_tools

NAME = "workspace_agent"


class WorkspaceAgent:
    """Answers questions about the workspace itself.

    "How many reports do we have in this workspace" needs neither a report nor
    a semantic model, only the workspace's listings -- yet with only a
    workspace selected, every question used to end at "open a report or
    semantic model and ask again".
    """

    name = NAME

    def gather_evidence(
        self,
        question: str,
        context: ResolvedAIContext,
    ) -> EvidenceBundle:
        inventory = context.workspace_inventory
        listed = inventory is not None and (
            inventory.reports is not None or inventory.semantic_models is not None
        )

        if not listed:
            return build_bundle(
                question=question,
                context=context,
                agent=NAME,
                evidence=[],
                status=AIAnswerStatus.INSUFFICIENT_EVIDENCE,
                missing_information=(
                    (inventory.notes if inventory else [])
                    or context.resolution_notes
                    or ["No workspace is in context. Pick a workspace and ask again."]
                ),
            )

        return build_bundle(
            question=question,
            context=context,
            agent=NAME,
            evidence=dossier_tools.workspace_dossier(context),
            status=AIAnswerStatus.ANSWERED,
        )
