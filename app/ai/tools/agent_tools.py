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

from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import VerificationStatus
from app.ai.models.evidence import EvidenceItem
from app.ai.tools import impact_tools, lineage_tools, measure_tools, report_tools


def _text(arguments: Mapping[str, Any], key: str) -> str:
    value = arguments.get(key)
    return value.strip() if isinstance(value, str) else ""


def _with_object(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> ResolvedAIContext:
    """Re-point the context at a named object, if one was supplied."""
    name = _text(arguments, "object_name") or _text(arguments, "measure_name")

    if not name:
        return context

    model = context.parsed_semantic_model
    if model is None:
        return context

    wanted_table = _text(arguments, "table_name").casefold()

    for table in model.tables:
        if wanted_table and table.name.casefold() != wanted_table:
            continue

        for measure in table.measures:
            if measure.name.casefold() == name.casefold():
                return _repoint(context, table.name, measure.name, "measure")

        for column in table.columns:
            if column.name.casefold() == name.casefold():
                object_type = "calculated_column" if column.expression else "column"
                return _repoint(context, table.name, column.name, object_type)

        if table.name.casefold() == name.casefold():
            return _repoint(context, table.name, table.name, "table")

    return context


def _repoint(
    context: ResolvedAIContext,
    table_name: str,
    object_name: str,
    object_type: str,
) -> ResolvedAIContext:
    qualified = table_name if object_type == "table" else f"{table_name}[{object_name}]"
    return context.model_copy(
        update={
            "resolved_object": ResolvedObject(
                object_type=object_type,
                table_name=table_name,
                object_name=object_name,
                qualified_name=qualified,
            )
        }
    )


def explain_object(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    """Definition, plain-language reading, upstream sources and impact."""
    scoped = _with_object(context, arguments)

    if scoped.resolved_object is None:
        return []

    if scoped.resolved_object.object_type == "measure":
        definition = measure_tools.get_measure_definition(scoped)
    else:
        definition = measure_tools.get_calculated_column_definition(scoped)

    return [
        *definition,
        *lineage_tools.get_upstream_lineage(scoped),
        *impact_tools.analyze_impact(scoped),
    ]


def object_lineage(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    scoped = _with_object(context, arguments)

    if scoped.resolved_object is None:
        return []

    direction = _text(arguments, "direction").casefold() or "upstream"

    if direction == "downstream":
        return [
            *lineage_tools.get_downstream_lineage(scoped),
            *impact_tools.analyze_impact(scoped),
        ]

    return lineage_tools.get_upstream_lineage(scoped)


def model_overview(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    return lineage_tools.get_semantic_model_details(context)


def physical_sources(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    return lineage_tools.get_physical_sources(context)


def report_overview(
    context: ResolvedAIContext,
    arguments: Mapping[str, Any],
) -> list[EvidenceItem]:
    return [
        *report_tools.get_report_summary(context),
        *report_tools.get_report_pages(context),
    ]


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
    query = _text(arguments, "query").casefold()
    model = context.parsed_semantic_model

    if not query or model is None:
        return []

    matches: list[dict[str, str]] = []

    for table in model.tables:
        if query in table.name.casefold():
            matches.append({"kind": "table", "table": table.name, "name": table.name})
        for measure in table.measures:
            if query in measure.name.casefold():
                matches.append(
                    {"kind": "measure", "table": table.name, "name": measure.name}
                )
        for column in table.columns:
            if query in column.name.casefold():
                matches.append(
                    {"kind": "column", "table": table.name, "name": column.name}
                )

    if not matches:
        return []

    return [
        EvidenceItem(
            evidence_id="",
            object_type="search_result",
            object_id=None,
            object_name=f"{len(matches)} match(es) for '{query}'",
            fact_type="relationship",
            source_type="tmdl",
            value={"matches": matches[:50]},
            workspace_id=context.workspace_id,
            semantic_model_id=context.semantic_model_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=datetime.now(UTC),
            source_reference=f"semantic_model:{context.semantic_model_id}",
        )
    ]
