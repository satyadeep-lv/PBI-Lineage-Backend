from app.ai.models.requests import AIChatContext

_MEASURE_SUGGESTIONS = [
    "Explain this measure",
    "What feeds this measure?",
    "What depends on this measure?",
    "What happens if this measure changes?",
]

_REPORT_SUGGESTIONS = [
    "Explain this report",
    "Which semantic model powers it?",
    "Where does the data come from?",
    "Which measures are used?",
]

_IMPACT_SUGGESTIONS = [
    "What depends on this object?",
    "What feeds this object?",
    "Which reports would be affected if this changes?",
]


def suggested_questions_for(context: AIChatContext | None) -> list[str]:
    """Deterministic, per-context suggestions — no model call needed."""
    object_type = (context.object_type if context else None) or ""

    if object_type in ("measure", "calculated_column"):
        return list(_MEASURE_SUGGESTIONS)
    if object_type == "report":
        return list(_REPORT_SUGGESTIONS)
    if object_type == "column":
        return list(_IMPACT_SUGGESTIONS)

    return []
