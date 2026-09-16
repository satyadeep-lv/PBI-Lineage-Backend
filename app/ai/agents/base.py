from typing import Protocol

from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus
from app.ai.models.evidence import EvidenceBundle, EvidenceConflict, EvidenceItem


class Agent(Protocol):
    name: str

    def gather_evidence(
        self,
        question: str,
        context: ResolvedAIContext,
    ) -> EvidenceBundle: ...


def assign_evidence_ids(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return [
        item.model_copy(update={"evidence_id": f"E{index + 1}"})
        for index, item in enumerate(items)
    ]


def build_bundle(
    *,
    question: str,
    context: ResolvedAIContext,
    agent: str,
    evidence: list[EvidenceItem],
    status: AIAnswerStatus,
    missing_information: list[str] | None = None,
    conflicts: list[EvidenceConflict] | None = None,
) -> EvidenceBundle:
    numbered = assign_evidence_ids(evidence)
    can_answer = status == AIAnswerStatus.ANSWERED and bool(numbered)

    return EvidenceBundle(
        question=question,
        context=context,
        evidence=numbered,
        can_answer=can_answer,
        status=status,
        agent=agent,
        missing_information=missing_information or [],
        conflicts=conflicts or [],
    )
