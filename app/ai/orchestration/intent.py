import re
from typing import Literal

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
    "what's in",
    "what is in",
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
# Things a workspace holds, as opposed to things inside one model.
_WORKSPACE_NOUNS = (
    "report",
    "semantic model",
    "dataset",
    "dashboard",
    "lakehouse",
    "notebook",
    "warehouse",
    "dataflow",
    "items",
)
_SOURCE_KEYWORDS = (
    "come from",
    "comes from",
    "source",
    "database",
)

# "What can you do?", "how do I use this?" -- a question about Power AI, which
# needs no lineage evidence and must never be refused for lacking it.
_HELP_PATTERN = re.compile(
    r"""
    \bwhat\s+(else\s+)?can\s+(you|power\s*ai|i)\s+(do|help|ask)\b
    | \bhow\s+can\s+(you|power\s*ai)\s+help\b
    | \bwhat\s+(do|does)\s+(you|power\s*ai)\s+do\b
    | \bwhat\s+(kind\s+of\s+|sort\s+of\s+)?(questions|things)\s+(can|should)\s+i\s+ask\b
    | \bwhat\s+should\s+i\s+ask\b
    | \bhow\s+(do\s+i|to)\s+use\s+(you|power\s*ai|this)\b
    | \bwho\s+are\s+you\b
    | \bwhat\s+are\s+you\s*[?.!]*\s*$
    | \bwhat\s+are\s+your\s+capabilities\b
    | \bwhat\s+is\s+power\s*ai\b
    | ^\s*help(\s+me)?\s*[?.!]*\s*$
    """,
    re.VERBOSE,
)
_GREETINGS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hiya",
        "yo",
        "good morning",
        "good afternoon",
        "good evening",
        "hi there",
        "hello there",
        "hey there",
        "hi power ai",
        "hello power ai",
        "hey power ai",
    }
)
_THANKS = frozenset(
    {
        "thanks",
        "thank you",
        "thanks a lot",
        "thank you so much",
        "many thanks",
        "cheers",
        "ok thanks",
        "ok thank you",
        "great thanks",
        "perfect thanks",
        "thx",
    }
)

CapabilityKind = Literal["greeting", "thanks", "help"]


def capability_kind(message: str) -> CapabilityKind | None:
    """Whether the message is about Power AI itself rather than the estate."""
    normalized = message.casefold().strip()
    words = " ".join(re.sub(r"[^\w\s]", " ", normalized).split())

    if words in _GREETINGS:
        return "greeting"
    if words in _THANKS:
        return "thanks"
    if _HELP_PATTERN.search(normalized):
        return "help"
    return None


def is_workspace_view(context: AIChatContext | None) -> bool:
    """A workspace is selected and nothing narrower is."""
    return bool(
        context
        and context.workspace_id
        and not (
            context.report_id
            or context.semantic_model_id
            or context.object_type
            or context.object_id
            or context.object_name
        )
    )


def _is_model_view(context: AIChatContext | None) -> bool:
    """A semantic model is open without a report or a selected object."""
    return bool(
        context
        and context.semantic_model_id
        and not (context.report_id or context.object_type or context.object_name)
    )


def _is_report_view(context: AIChatContext | None) -> bool:
    """A report is open, sent without an explicit object type."""
    return bool(context and context.report_id and not context.object_type)


def wants_workspace_inventory(
    message: str,
    context: AIChatContext | None,
) -> bool:
    """Whether answering needs the workspace's reports and semantic models.

    Only then are they listed: every other question is about something already
    open, and the listing would only add latency to it.
    """
    if context is None or not context.workspace_id:
        return False
    if is_workspace_view(context):
        return True

    normalized = message.casefold()
    if classify_intent(message, context) == AIIntent.WORKSPACE_INFORMATION:
        return True
    return _mentions(normalized, _INVENTORY_KEYWORDS) and _mentions(
        normalized, _WORKSPACE_NOUNS
    )


def classify_intent(
    message: str,
    context: AIChatContext | None,
) -> AIIntent:
    """Deterministic-first intent routing.

    No model call is made here: this is a pure function of the question
    text and the (unresolved, hint-only) context the client supplied. Only
    genuinely ambiguous phrasing outside these rules falls through to
    OUT_OF_SCOPE (the tool-calling loop, when a model is available, is what
    answers phrasing no rule anticipated).
    """
    normalized = message.casefold()
    object_type = (context.object_type if context else None) or ""
    about_impact = _mentions(normalized, _IMPACT_KEYWORDS)

    if capability_kind(message) is not None:
        return AIIntent.CAPABILITIES

    # "How many reports are in this workspace" is about the workspace even
    # while a report or measure happens to be open.
    if "workspace" in normalized and not about_impact:
        return AIIntent.WORKSPACE_INFORMATION

    # With a report open, "which measures are used" means used by *this
    # report*, and "where does the data come from" means its sources -- the
    # report agent's evidence answers both, where the model inventory would
    # list every measure in the model instead.
    if object_type == "report" and not about_impact:
        return AIIntent.REPORT_INFORMATION

    # Checked before the object-type hint: "what measures are there" is an
    # inventory question even while a measure happens to be selected.
    if _mentions(normalized, _INVENTORY_KEYWORDS):
        # With only a workspace open, "how many reports" is about the
        # workspace; "what measures are there" still needs a model.
        if is_workspace_view(context) and _mentions(normalized, _WORKSPACE_NOUNS):
            return AIIntent.WORKSPACE_INFORMATION
        return AIIntent.SEMANTIC_MODEL_INFORMATION

    if about_impact:
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

    if object_type == "table":
        return AIIntent.OBJECT_IMPACT

    # With only a workspace open, a question about the view or about its
    # reports and models is a question about the workspace.
    if is_workspace_view(context) and (
        _mentions(normalized, _CONTEXT_KEYWORDS)
        or _mentions(normalized, _WORKSPACE_NOUNS)
    ):
        return AIIntent.WORKSPACE_INFORMATION

    # With only a model open, "what's in it" and "where does its data come
    # from" are answered by the model overview, not by a report agent that
    # has no report to read.
    if _is_model_view(context) and (
        _mentions(normalized, _CONTEXT_KEYWORDS)
        or _mentions(normalized, _REPORT_KEYWORDS)
        or _mentions(normalized, _SOURCE_KEYWORDS)
    ):
        return AIIntent.SEMANTIC_MODEL_INFORMATION

    # The same for an open report whose type the client did not state:
    # "where does the data come from" is about that report's sources.
    if _is_report_view(context) and (
        _mentions(normalized, _CONTEXT_KEYWORDS)
        or _mentions(normalized, _REPORT_KEYWORDS)
        or _mentions(normalized, _SOURCE_KEYWORDS)
    ):
        return AIIntent.REPORT_INFORMATION

    # No object-type hint: describing the current view comes before generic
    # verbs like "explain", which say nothing about *what* to explain.
    if _mentions(normalized, _CONTEXT_KEYWORDS):
        return AIIntent.SEMANTIC_MODEL_INFORMATION

    if _mentions(normalized, _MEASURE_KEYWORDS):
        return AIIntent.MEASURE_EXPLANATION

    if _mentions(normalized, _REPORT_KEYWORDS):
        return AIIntent.REPORT_INFORMATION

    return AIIntent.OUT_OF_SCOPE


def _mentions(normalized: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in normalized for keyword in keywords)
