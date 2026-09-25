from typing import Any

from app.ai.composition.evidence_sections import grouped_by_section
from app.ai.composition.persona import include_internal_ids
from app.ai.models.enums import AIAnswerStatus, AudienceType
from app.ai.models.evidence import EvidenceBundle, EvidenceItem

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I could not determine this from the currently available lineage evidence."
)

# Object ids that are already part of the rendered line, or are opaque
# hashes a reader cannot act on, are not repeated in developer mode.
_UNHELPFUL_ID_TYPES = frozenset(
    {
        "visual",
        "coverage",
        "context",
        "physical_source",
        "report",
        "report_page",
        "semantic_model",
        "semantic_table",
        "relationship",
        "search_result",
    }
)

_DAX_INDENT = "    "


class DeterministicAnswerRenderer:
    """Renders an answer straight from an EvidenceBundle, no model call.

    Used for every non-`answered` status, and as the fallback whenever the
    grounded composer/validator path fails for an otherwise-answered
    bundle — this is what keeps Power AI factually functional even when
    model composition breaks.

    The output is plain text laid out as short titled sections, because the
    chat panel renders it verbatim: no Markdown markers to show up as
    literal asterisks, and DAX indented so it still reads as a code block
    wherever Markdown is rendered.
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
    blocks: list[list[str]] = []

    # An answered bundle can still carry a note -- e.g. the object asked
    # about could not be resolved, so this is the model overview instead.
    # Saying so up front keeps the fallback from reading as a non sequitur.
    if bundle.missing_information:
        blocks.append([f"Note: {note}" for note in bundle.missing_information])

    definitions = [item for item in bundle.evidence if item.fact_type == "definition"]
    plain = [item for item in definitions if item.plain_language]
    # One object being explained: lead with its plain-language reading. A
    # model overview has a reading per measure, so those stay inline.
    lead_plain = len(plain) == 1

    for section, items in grouped_by_section(bundle.evidence):
        if section.title == "Context":
            blocks.insert(
                0 if not bundle.missing_information else 1,
                [_line(item) for item in items],
            )
            continue

        if section.title == "Definition" and lead_plain:
            blocks.append(["In plain English", plain[0].plain_language or ""])

        lines = [section.title]
        for item in items:
            if item.fact_type == "definition":
                lines.extend(
                    _definition_lines(
                        item, show_ids=show_ids, inline_plain=not lead_plain
                    )
                )
            else:
                lines.append(f"- {_line(item, show_ids=show_ids)}")
        blocks.append(lines)

    if not blocks or all(block[0].startswith("Note:") for block in blocks):
        return INSUFFICIENT_EVIDENCE_MESSAGE

    return "\n\n".join("\n".join(block) for block in blocks)


def _definition_lines(
    item: EvidenceItem,
    *,
    show_ids: bool,
    inline_plain: bool,
) -> list[str]:
    if isinstance(item.value, dict):
        # A model, report or column summary rather than an expression --
        # printing the raw dict here was how "what is in this model" came out
        # as an unreadable blob.
        summary = item.display_value or _summary_label(item.value)
        if item.object_name not in summary:
            summary = f"{item.object_name}: {summary}"
        return [f"- {summary}"]

    header = item.object_name
    if item.display_value:
        header += f" ({item.display_value})"
    if inline_plain and item.plain_language:
        header += f": {item.plain_language}"

    lines = [f"- {header}"]
    lines.extend(
        f"{_DAX_INDENT}{line.rstrip()}"
        for line in str(item.value).strip().splitlines()
        if line.strip()
    )
    if show_ids and item.source_reference:
        lines.append(f"{_DAX_INDENT}Defined in: {item.source_reference}")
    return lines


def _line(item: EvidenceItem, *, show_ids: bool = False) -> str:
    text = item.display_value or _value_label(item.value) or item.object_name

    if (
        show_ids
        and item.object_id
        and item.object_type not in _UNHELPFUL_ID_TYPES
        and item.object_id not in text
    ):
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
