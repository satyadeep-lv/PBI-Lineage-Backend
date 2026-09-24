from typing import Any

from app.ai.composition.persona import include_internal_ids
from app.ai.models.enums import AIAnswerStatus, AudienceType
from app.ai.models.evidence import EvidenceBundle, EvidenceItem

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I could not determine this from the currently available lineage evidence."
)

_SECTION_LABELS: tuple[tuple[str, str], ...] = (
    ("definition", "Definition"),
    ("dependency", "Depends on (semantic model)"),
    ("source", "Reads from (database)"),
    ("usage", "Used by"),
    ("impact", "Downstream impact"),
    ("relationship", "Related objects"),
)


class DeterministicAnswerRenderer:
    """Renders an answer straight from an EvidenceBundle, no model call.

    Used for every non-`answered` status, and as the fallback whenever the
    grounded composer/validator path fails for an otherwise-answered
    bundle — this is what keeps Power AI factually functional even when
    model composition breaks.
    """

    @staticmethod
    def render(
        bundle: EvidenceBundle,
        audience: AudienceType,
    ) -> str:
        if bundle.status == AIAnswerStatus.INSUFFICIENT_EVIDENCE:
            return _render_insufficient(bundle)
        if bundle.status == AIAnswerStatus.AMBIGUOUS:
            return _render_ambiguous(bundle)
        if bundle.status == AIAnswerStatus.CONFLICTING_EVIDENCE:
            return _render_conflicting(bundle)
        if bundle.status == AIAnswerStatus.OUT_OF_SCOPE:
            return _render_out_of_scope(bundle)
        return _render_from_evidence(bundle, audience)


def _render_insufficient(bundle: EvidenceBundle) -> str:
    return "\n".join([INSUFFICIENT_EVIDENCE_MESSAGE, *bundle.missing_information])


def _render_ambiguous(bundle: EvidenceBundle) -> str:
    lines = [
        "I found more than one possible match and need a more specific "
        "reference before I can answer."
    ]
    lines.extend(bundle.missing_information)
    return "\n".join(lines)


def _render_conflicting(bundle: EvidenceBundle) -> str:
    lines = [
        "The definition and runtime metadata for this object disagree, so "
        "I cannot give one authoritative answer:"
    ]
    for conflict in bundle.conflicts:
        lines.append(f"- {conflict.object_name} ({conflict.field}):")
        lines.append(f"  Definition (TMDL): {conflict.definition_value}")
        lines.append(f"  Runtime (XMLA): {conflict.runtime_value}")
    return "\n".join(lines)


def _render_out_of_scope(bundle: EvidenceBundle) -> str:
    if bundle.missing_information:
        return "\n".join(bundle.missing_information)
    return "This question is outside Power AI's current scope."


def _render_from_evidence(
    bundle: EvidenceBundle,
    audience: AudienceType,
) -> str:
    show_ids = include_internal_ids(audience)
    sections: dict[str, list[str]] = {}

    for item in bundle.evidence:
        sections.setdefault(item.fact_type, []).append(
            _render_item(item, show_ids=show_ids)
        )

    lines: list[str] = []

    # Lead with the plain-language restatement: it is the part a reader
    # without DAX can act on, and it is derived, not generated, so it is
    # always present.
    plain = [item.plain_language for item in bundle.evidence if item.plain_language]
    if plain:
        lines.append("In plain English:")
        lines.extend(f"- {entry}" for entry in plain)

    for fact_type, label in _SECTION_LABELS:
        entries = sections.get(fact_type)
        if not entries:
            continue
        lines.append(f"{label}:")
        lines.extend(f"- {entry}" for entry in entries)

    if not lines:
        return INSUFFICIENT_EVIDENCE_MESSAGE

    return "\n".join(lines)


def _render_item(item: EvidenceItem, *, show_ids: bool) -> str:
    if item.fact_type == "definition":
        if isinstance(item.value, dict):
            # A model or report summary, not a DAX expression -- printing the
            # raw dict here was how "what is in this model" came out as an
            # unreadable blob.
            return f"{item.object_name}: {_summary_label(item.value)}"
        return f"{item.object_name}: {item.value}"

    text = _value_label(item.value) or item.object_name

    if show_ids and item.object_id:
        text = f"{text} ({item.object_id})"

    return text


def _value_label(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None

    properties = value.get("properties")

    if value.get("node_type") == "visual" and isinstance(properties, dict):
        return _visual_label(properties)

    if "qualified_name" in value:
        return str(value["qualified_name"])

    return None


def _summary_label(value: dict[str, Any]) -> str:
    parts: list[str] = []

    for key, noun in (
        ("table_count", "table"),
        ("measure_count", "measure"),
        ("column_count", "column"),
        ("page_count", "page"),
        ("visual_count", "visual"),
    ):
        count = value.get(key)
        if isinstance(count, int):
            parts.append(f"{count} {noun}{'' if count == 1 else 's'}")

    tables = value.get("table_names")
    if isinstance(tables, list) and tables:
        parts.append(f"tables: {', '.join(str(name) for name in tables)}")

    measures = value.get("measures_by_table")
    if isinstance(measures, dict) and measures:
        for table, names in measures.items():
            if names:
                joined = ", ".join(str(name) for name in names)
                parts.append(f"measures in {table}: {joined}")

    if not parts:
        return ", ".join(f"{key}={val}" for key, val in value.items())

    return "; ".join(parts)


def _visual_label(properties: dict[str, Any]) -> str:
    """Name a visual by what a report author would recognise.

    A visual's node name falls back to its GUID when it has no title, so
    without this the only thing shown for "what breaks if this changes" was
    an unreadable identifier.
    """
    title = properties.get("visual_title")
    visual_type = properties.get("visual_type")
    page = properties.get("page_display_name") or properties.get("page_name")

    name = title or (f"{visual_type} visual" if visual_type else "visual")

    if title and visual_type:
        name = f"{title} ({visual_type})"

    if page:
        return f"{name} on page '{page}'"

    return name
