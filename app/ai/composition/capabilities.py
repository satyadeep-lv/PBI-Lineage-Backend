"""Answers to questions about Power AI itself: "what can you do?", "hi".

These are not questions about the estate, so there is no lineage evidence to
gather and nothing to refuse for lacking it -- yet "What can Power AI help me
with here?" used to end at "I need a bit more to go on". The answer is written
deterministically from what is open, and the only facts it states (how many
reports a workspace has, what a report is built on) are the same evidence
items the dossiers produce, returned alongside it.
"""

from app.ai.models.context import ResolvedAIContext
from app.ai.models.evidence import EvidenceItem
from app.ai.orchestration.intent import CapabilityKind
from app.ai.tools import dossier_tools

_INTRODUCTION = (
    "I answer questions about your Power BI content from its real "
    "definitions: reports, semantic models, their DAX, and the databases "
    "behind them."
)

_REPORT_ABILITIES = [
    "This report: what each page and visual shows, which measures and "
    "columns it uses, and which semantic model powers it.",
    "Where its data comes from: the database, schema and tables behind every field.",
]
_MODEL_ABILITIES = [
    "Any measure or column: its DAX in plain English, what it depends on, "
    "and the database tables behind it.",
    "Impact: which measures, tables and report visuals would break if "
    "something changed.",
    "The model itself: its tables, relationships, measures and data sources.",
]
_WORKSPACE_ABILITIES = [
    "This workspace: its reports, semantic models and other items, and which "
    "semantic model each report uses.",
    "Open a report or semantic model and I can also explain its measures in "
    "plain English, trace where its data comes from, and show what would "
    "break if something changed.",
]
_GENERAL_ABILITIES = [
    "Pick a workspace and I can tell you what it contains.",
    "Open a report or semantic model and I can explain its measures, trace "
    "where its data comes from, and show what would break if something "
    "changed.",
]


def capabilities_answer(
    context: ResolvedAIContext,
    *,
    kind: CapabilityKind,
    suggestions: list[str],
) -> tuple[str, list[EvidenceItem]]:
    """The answer text, and the evidence behind any fact it states."""
    if kind == "thanks":
        lines = ["You're welcome."]
        if suggestions:
            lines += ["", "Anything else? You could ask:"]
            lines += [f"- {question}" for question in suggestions]
        return "\n".join(lines), []

    evidence = _scope_evidence(context)
    opening = ("Hi! I'm Power AI. " if kind == "greeting" else "") + _INTRODUCTION

    blocks = [[opening]]
    if evidence:
        blocks.append(
            ["What you have open"] + [f"- {item.display_value}" for item in evidence]
        )
    blocks.append(
        ["What I can help with"] + [f"- {line}" for line in _abilities(context)]
    )
    if suggestions:
        blocks.append(["Try asking"] + [f"- {question}" for question in suggestions])

    return "\n\n".join("\n".join(block) for block in blocks), evidence


def _scope_evidence(context: ResolvedAIContext) -> list[EvidenceItem]:
    """The one-line summary of each thing in view: report, model, workspace."""
    evidence: list[EvidenceItem] = []
    for dossier in (
        dossier_tools.report_dossier,
        dossier_tools.model_dossier,
        dossier_tools.workspace_dossier,
    ):
        summary = next(
            (item for item in dossier(context) if item.fact_type == "definition"),
            None,
        )
        if summary is not None and summary.display_value:
            evidence.append(summary)
    return evidence


def _abilities(context: ResolvedAIContext) -> list[str]:
    abilities: list[str] = []
    if context.report_definition is not None:
        abilities += _REPORT_ABILITIES
    if context.parsed_semantic_model is not None:
        abilities += _MODEL_ABILITIES
    if abilities:
        return abilities
    if context.workspace_id:
        return list(_WORKSPACE_ABILITIES)
    return list(_GENERAL_ABILITIES)
