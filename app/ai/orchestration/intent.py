from app.ai.models.enums import AIIntent
from app.ai.models.requests import AIChatContext

_IMPACT_KEYWORDS = (
    "impact",
    "depend",
    "what happens if",
    "upstream",
    "downstream",
    "removed",
    "remove",
    "changes",
    "change",
    "affect",
)
_MEASURE_KEYWORDS = (
    "explain",
    "what is",
    "how is",
    "calculated",
    "definition",
    "dax",
    "measure",
)
# Asking what exists is a different question from asking about one object,
# and must not be routed to an agent that needs a specific object resolved.
_INVENTORY_KEYWORDS = (
    "how many",
    "how much",
    "list ",
    "what are",
    "which are",
    "what measures",
    "which measures",
    "what tables",
    "which tables",
    "what columns",
    "which columns",
    "what reports",
    "which reports",
)
# Asking about the current view, when nothing specific is selected.
_CONTEXT_KEYWORDS = (
    "looking at",
    "what am i",
    "overview",
    "summarise",
    "summarize",
    "summary",
    "what can you",
    "what can power ai",
    "help me with",
)
_REPORT_KEYWORDS = (
    "report",
    "semantic model",
    "page",
    "visual",
)


def classify_intent(
    message: str,
    context: AIChatContext | None,
) -> AIIntent:
    """Deterministic-first intent routing.

    No model call is made here: this is a pure function of the question
    text and the (unresolved, hint-only) object type the client supplied.
    Only genuinely ambiguous phrasing outside these rules falls through to
    OUT_OF_SCOPE in this phase (an LLM router is not needed yet — every
    intent this phase implements is already covered deterministically).
    """
    normalized = message.casefold()
    object_type = (context.object_type if context else None) or ""

    # Checked before the object-type hint: "what measures are there" is an
    # inventory question even while a measure happens to be selected.
    if any(keyword in normalized for keyword in _INVENTORY_KEYWORDS):
        return AIIntent.SEMANTIC_MODEL_INFORMATION

    if any(keyword in normalized for keyword in _IMPACT_KEYWORDS):
        return AIIntent.OBJECT_IMPACT

    # A client-declared object type is a stronger, more specific signal
    # than a generic verb like "explain" (which says nothing about *what*
    # is being explained) — so it takes priority over keyword inference.
    if object_type == "calculated_column":
        return AIIntent.CALCULATED_COLUMN_EXPLANATION

    if object_type == "measure":
        return AIIntent.MEASURE_EXPLANATION

    if object_type == "column":
        # A plain (non-calculated) column has no DAX definition of its own;
        # "explain"/"what happens if" questions about it are inherently
        # lineage/impact questions.
        return AIIntent.OBJECT_IMPACT

    if object_type == "report":
        return AIIntent.REPORT_INFORMATION

    # No object-type hint: describing the current view comes before generic
    # verbs like "explain", which say nothing about *what* to explain.
    if any(keyword in normalized for keyword in _CONTEXT_KEYWORDS):
        return AIIntent.SEMANTIC_MODEL_INFORMATION

    if any(keyword in normalized for keyword in _MEASURE_KEYWORDS):
        return AIIntent.MEASURE_EXPLANATION

    if any(keyword in normalized for keyword in _REPORT_KEYWORDS):
        return AIIntent.REPORT_INFORMATION

    return AIIntent.OUT_OF_SCOPE
