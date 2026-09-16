from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus, VerificationStatus

EvidenceFactType = Literal[
    "definition",
    "dependency",
    "relationship",
    "source",
    "usage",
    "impact",
]

EvidenceSourceType = Literal[
    "pbir",
    "tmdl",
    "xmla",
    "scanner",
    "lineage_graph",
    "snowflake",
    "other",
]


class EvidenceItem(BaseModel):
    """One fact, traceable to exactly one deterministic backend call.

    Never constructed from model output — only from a real service
    response. `source_reference` should point at something a reader could
    independently verify (a TMDL source_path, a lineage graph edge/node id).
    """

    evidence_id: str

    object_type: str
    object_id: str | None = None
    object_name: str

    fact_type: EvidenceFactType
    source_type: EvidenceSourceType

    value: Any

    workspace_id: str | None = None
    report_id: str | None = None
    semantic_model_id: str | None = None

    verification_status: VerificationStatus

    retrieved_at: datetime

    source_reference: str | None = None


class EvidenceConflict(BaseModel):
    field: str
    definition_value: Any
    runtime_value: Any
    object_name: str


class EvidenceBundle(BaseModel):
    """Everything an agent gathered for one question, plus the verdict on
    whether it is sufficient to answer factually at all.

    The model is only ever shown this bundle when `can_answer` is True.
    """

    question: str

    context: ResolvedAIContext

    evidence: list[EvidenceItem] = Field(default_factory=list)

    can_answer: bool

    status: AIAnswerStatus

    agent: str | None = None

    missing_information: list[str] = Field(default_factory=list)

    conflicts: list[EvidenceConflict] = Field(default_factory=list)


class GroundedClaim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(min_length=1)
