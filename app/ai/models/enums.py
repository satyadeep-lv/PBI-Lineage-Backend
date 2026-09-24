from enum import Enum


class AudienceType(str, Enum):
    GENERAL = "general"
    BUSINESS = "business"
    DEVELOPER = "developer"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AIAnswerStatus(str, Enum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    AMBIGUOUS = "ambiguous"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    OUT_OF_SCOPE = "out_of_scope"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


class AIIntent(str, Enum):
    MEASURE_EXPLANATION = "measure_explanation"
    CALCULATED_COLUMN_EXPLANATION = "calculated_column_explanation"
    REPORT_INFORMATION = "report_information"
    SEMANTIC_MODEL_INFORMATION = "semantic_model_information"
    DATABASE_SOURCE = "database_source"
    UPSTREAM_LINEAGE = "upstream_lineage"
    DOWNSTREAM_LINEAGE = "downstream_lineage"
    OBJECT_IMPACT = "object_impact"
    GENERAL_LINEAGE_QUESTION = "general_lineage_question"
    OUT_OF_SCOPE = "out_of_scope"
