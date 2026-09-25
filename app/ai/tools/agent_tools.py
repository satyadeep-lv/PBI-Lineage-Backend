"""Argument-taking wrappers over the deterministic evidence tools.

The per-object tools all answer questions about `context.resolved_object`,
which the UI had to have resolved first. That is why a question naming an
object the user had not clicked could not be answered at all. These wrappers
let a caller -- including a model choosing a tool -- name the object instead.

Resolution happens strictly inside the already-fetched, already-authorized
`ResolvedAIContext`. An object the caller cannot see simply does not match,
so naming one returns no evidence rather than widening access.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.ai.context.semantic_objects import find_semantic_object, split_qualified_name
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import VerificationStatus
from app.ai.models.evidence import EvidenceItem
from app.ai.tools import dossier_tools, report_tools

_UPSTREAM_FACTS = frozenset({"dependency", "source"})
_DOWNSTREAM_FACTS = frozenset({"impact"})


def _text(arguments: Mapping[str, Any], key: str) -> str:
    value = arguments.get(key)
    return value.strip() if isinstance(value, str) else ""


def _with_object(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> ResolvedAIContext:
    """Re-point the context at a named object, if one was supplied."""
    name = _text(arguments, "object_name") or _text(arguments, "measure_name")
    model = context.parsed_semantic_model

    if not name or model is None:
        return context

    found = find_semantic_object(
        model,
        name,
        table_name=_text(arguments, "table_name") or None,
    )
    if found is None:
        # A name the model does not hold must not silently fall back to the
        # selected object and answer about something else.
        return context.model_copy(update={"resolved_object": None})

    return context.model_copy(update={"resolved_object": found})


def explain_object(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    """The full picture of one object: definition, lineage and impact."""
    return dossier_tools.object_dossier(_with_object(context, arguments))


def object_lineage(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    dossier = dossier_tools.object_dossier(_with_object(context, arguments))
    direction = _text(arguments, "direction").casefold() or "upstream"
    wanted = _DOWNSTREAM_FACTS if direction == "downstream" else _UPSTREAM_FACTS

    return [
        item
        for item in dossier
        if item.fact_type in wanted or item.object_type in ("context", "coverage")
    ]


def model_overview(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    return dossier_tools.model_dossier(context)


def physical_sources(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    return [
        item
        for item in dossier_tools.model_dossier(context)
        if item.fact_type == "source"
        or item.object_type in ("semantic_table", "coverage")
    ]


def report_overview(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    return dossier_tools.report_dossier(context)


def report_visuals(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    return report_tools.get_report_visuals(context)


def search_model(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    """Find objects by name fragment, so the model can locate a target.

    The reference implementation leans on a broad "search everything" tool
    before drilling in; this is the same idea bounded to the semantic model
    already in context.
    """
    raw_query = _text(arguments, "query")
    model = context.parsed_semantic_model

    if not raw_query or model is None:
        return []

    table_filter, name = split_qualified_name(raw_query)
    query = name.casefold()
    wanted_table = (table_filter or "").casefold()

    matches: list[dict[str, str]] = []

    for table in model.tables:
        if wanted_table and table.name.casefold() != wanted_table:
            continue
        if not wanted_table and query in table.name.casefold():
            matches.append({"kind": "table", "table": table.name, "name": table.name})
        for measure in table.measures:
            if query in measure.name.casefold():
                matches.append(
                    {"kind": "measure", "table": table.name, "name": measure.name}
                )
        for column in table.columns:
            if query in column.name.casefold():
                matches.append(
                    {
                        "kind": "calculated column" if column.expression else "column",
                        "table": table.name,
                        "name": column.name,
                    }
                )

    if not matches:
        return []

    listed = matches[:50]
    return [
        EvidenceItem(
            evidence_id="",
            object_type="search_result",
            object_id=None,
            object_name=f"{len(matches)} match(es) for '{raw_query}'",
            fact_type="relationship",
            source_type="tmdl",
            value={"matches": listed},
            display_value="; ".join(
                f"{match['table']}[{match['name']}] ({match['kind']})"
                if match["kind"] != "table"
                else f"{match['name']} (table)"
                for match in listed
            ),
            workspace_id=context.workspace_id,
            semantic_model_id=context.semantic_model_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=datetime.now(UTC),
            source_reference=f"semantic_model:{context.semantic_model_id}",
        )
    ]
