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

_MODEL_SUGGESTIONS = [
    "What's in this semantic model?",
    "Which measures does it have?",
    "Where does its data come from?",
    "Which reports use this semantic model?",
]

_WORKSPACE_SUGGESTIONS = [
    "What's in this workspace?",
    "How many reports are in this workspace?",
    "Which semantic models are in this workspace?",
    "Which semantic model does each report use?",
]

_GENERAL_SUGGESTIONS = [
    "What can Power AI help me with?",
]


def suggested_questions_for(context: AIChatContext | None) -> list[str]:
    """Deterministic, per-context suggestions — no model call needed.

    Every suggestion is one the router answers for that context, so a click
    on one never ends at "I need a bit more to go on".
    """
    object_type = (context.object_type if context else None) or ""

    if object_type in ("measure", "calculated_column"):
        return list(_MEASURE_SUGGESTIONS)
    if object_type == "report" or (context and context.report_id):
        return list(_REPORT_SUGGESTIONS)
    if object_type in ("column", "table"):
        return list(_IMPACT_SUGGESTIONS)
    if context and context.semantic_model_id:
        return list(_MODEL_SUGGESTIONS)
    if context and context.workspace_id:
        return list(_WORKSPACE_SUGGESTIONS)

    return list(_GENERAL_SUGGESTIONS)
