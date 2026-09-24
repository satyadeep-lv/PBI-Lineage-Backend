from app.ai.models.enums import AudienceType

_PERSONA_PROMPT_HINTS: dict[AudienceType, str] = {
    AudienceType.GENERAL: (
        "Write for a general reader with no technical background. Lead with "
        "plain language and business meaning; show the DAX once, verbatim, "
        "and explain it in everyday words rather than walking through "
        "syntax. Leave out internal identifiers."
    ),
    AudienceType.BUSINESS: (
        "Write for a business/KPI-focused reader. Emphasize business "
        "meaning, business impact, and which reports and visuals would be "
        "affected, with the DAX shown once and a brief source overview. "
        "Avoid raw internal identifiers unless needed."
    ),
    AudienceType.DEVELOPER: (
        "Write for a developer/analyst. Include exact DAX, table/model "
        "names, and full technical dependency/impact details straight from "
        "the evidence -- every upstream object, database table and column, "
        "dependent object and affected visual."
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
