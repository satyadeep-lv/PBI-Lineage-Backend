"""Which section of an answer each evidence item belongs to.

Shared by the deterministic renderer and by every prompt that shows evidence
to a model, so the answer a reader gets without a provider is organised the
same way as the evidence a model is asked to write from.
"""

from dataclasses import dataclass

from app.ai.models.evidence import EvidenceItem


@dataclass(frozen=True)
class Section:
    order: int
    title: str


_CONTEXT = Section(0, "Context")
_ABOUT_REPORT = Section(5, "About this report")
_ABOUT_MODEL = Section(6, "About this semantic model")
_DEFINITION = Section(10, "Definition")
_REPORT_PAGES = Section(20, "Pages and visuals")
_REPORT_FIELDS = Section(22, "Measures and columns its visuals use")
_MODEL_TABLES = Section(25, "Tables in the model")
_RELATIONSHIPS = Section(28, "Relationships")
_DEPENDENCY = Section(30, "Depends on (semantic model lineage)")
_SOURCE = Section(40, "Reads from (database lineage)")
_DEPENDENTS = Section(50, "Measures and columns built on it")
_TABLE_IMPACT = Section(55, "Tables affected")
_VISUAL_IMPACT = Section(60, "Visual impact")
_VISUAL_FIELDS = Section(62, "Visuals and the fields they use")
_REPORTS = Section(65, "Reports using this semantic model")
_RELATED = Section(70, "Related objects")
_COVERAGE = Section(90, "What was checked")

_BY_FACT_AND_OBJECT: dict[tuple[str, str], Section] = {
    ("relationship", "context"): _CONTEXT,
    ("definition", "report"): _ABOUT_REPORT,
    ("definition", "semantic_model"): _ABOUT_MODEL,
    ("usage", "measure"): _REPORT_FIELDS,
    ("usage", "column"): _REPORT_FIELDS,
    ("usage", "calculated_column"): _REPORT_FIELDS,
    ("usage", "hierarchy"): _REPORT_FIELDS,
    ("usage", "hierarchy_level"): _REPORT_FIELDS,
    ("relationship", "coverage"): _COVERAGE,
    ("relationship", "report_page"): _REPORT_PAGES,
    ("relationship", "semantic_table"): _MODEL_TABLES,
    ("relationship", "relationship"): _RELATIONSHIPS,
    ("impact", "semantic_table"): _TABLE_IMPACT,
    # A visual an object reaches is impact ("what breaks if it changes");
    # a report's own visual listing is usage.
    ("impact", "visual"): _VISUAL_IMPACT,
    ("impact", "report"): _VISUAL_IMPACT,
    ("impact", "report_page"): _VISUAL_IMPACT,
    ("usage", "report"): _REPORTS,
    ("usage", "visual"): _VISUAL_FIELDS,
}

_BY_FACT: dict[str, Section] = {
    "definition": _DEFINITION,
    "dependency": _DEPENDENCY,
    "source": _SOURCE,
    "impact": _DEPENDENTS,
    "usage": _VISUAL_FIELDS,
    "relationship": _RELATED,
}


def section_for(item: EvidenceItem) -> Section:
    return _BY_FACT_AND_OBJECT.get(
        (item.fact_type, item.object_type),
        _BY_FACT.get(item.fact_type, _RELATED),
    )


def grouped_by_section(
    evidence: list[EvidenceItem],
) -> list[tuple[Section, list[EvidenceItem]]]:
    """Evidence in reading order, one group per section, input order kept."""
    groups: dict[Section, list[EvidenceItem]] = {}
    for item in evidence:
        groups.setdefault(section_for(item), []).append(item)
    return sorted(groups.items(), key=lambda entry: entry[0].order)


def describe_evidence(item: EvidenceItem) -> str:
    """One evidence item as a model should read it: the fact, then the DAX."""
    text = f"{item.object_type} '{item.object_name}'"
    if item.display_value:
        text += f": {item.display_value}"
    if item.plain_language:
        text += f"\n    Plain language: {item.plain_language}"
    if item.fact_type == "definition" and isinstance(item.value, str):
        text += f"\n    DAX: {item.value}"
    elif not item.display_value:
        text += f": {item.value!r}"
    return text
