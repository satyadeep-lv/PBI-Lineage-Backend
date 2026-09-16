from app.ai.models.enums import AudienceType

_PERSONA_PROMPT_HINTS: dict[AudienceType, str] = {
    AudienceType.GENERAL: (
        "Write for a general reader with no technical background. Use plain "
        "language, explain business meaning, and avoid DAX/SQL syntax and "
        "internal identifiers unless the reader explicitly asked for them."
    ),
    AudienceType.BUSINESS: (
        "Write for a business/KPI-focused reader. Emphasize business "
        "meaning, business impact, and which dependencies/reports matter, "
        "with a brief source overview. Avoid raw internal identifiers "
        "unless needed."
    ),
    AudienceType.DEVELOPER: (
        "Write for a developer/analyst. Include exact DAX, table/model "
        "names, and full technical dependency/impact details straight from "
        "the evidence, including object identifiers where useful."
    ),
}


def persona_prompt_hint(audience: AudienceType) -> str:
    return _PERSONA_PROMPT_HINTS[audience]


def include_internal_ids(audience: AudienceType) -> bool:
    """Persona changes presentation only, never which evidence exists.

    This only controls whether the deterministic renderer prints raw
    object ids alongside names — it never changes tool calls, evidence
    retrieval, or authorization.
    """
    return audience == AudienceType.DEVELOPER
