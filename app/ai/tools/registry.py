from app.ai.tools import impact_tools, lineage_tools, measure_tools, report_tools
from app.ai.tools.base import Tool

_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="measure.definition",
        description=(
            "Retrieve the exact DAX definition of the resolved measure from TMDL."
        ),
        requires_context=frozenset({"semantic_model", "resolved_object"}),
        handler=measure_tools.get_measure_definition,
    ),
    Tool(
        name="column.definition",
        description=(
            "Retrieve the exact DAX definition of the resolved calculated "
            "column from TMDL."
        ),
        requires_context=frozenset({"semantic_model", "resolved_object"}),
        handler=measure_tools.get_calculated_column_definition,
    ),
    Tool(
        name="report.summary",
        description=(
            "Retrieve report format, page/visual counts, and semantic model reference."
        ),
        requires_context=frozenset({"report_definition"}),
        handler=report_tools.get_report_summary,
    ),
    Tool(
        name="report.pages",
        description="Retrieve report page metadata.",
        requires_context=frozenset({"report_definition"}),
        handler=report_tools.get_report_pages,
    ),
    Tool(
        name="report.visuals",
        description="Retrieve report visuals and the semantic fields they use.",
        requires_context=frozenset({"report_definition"}),
        handler=report_tools.get_report_visuals,
    ),
    Tool(
        name="semantic_model.details",
        description=(
            "Retrieve semantic model table/column/measure counts and table names."
        ),
        requires_context=frozenset({"semantic_model"}),
        handler=lineage_tools.get_semantic_model_details,
    ),
    Tool(
        name="source.physical",
        description=(
            "Retrieve the physical data sources detected for the semantic model."
        ),
        requires_context=frozenset({"semantic_model"}),
        handler=lineage_tools.get_physical_sources,
    ),
    Tool(
        name="lineage.upstream",
        description=(
            "Retrieve what the resolved object depends on "
            "(bounded-depth upstream lineage)."
        ),
        requires_context=frozenset({"semantic_model", "resolved_object"}),
        handler=lineage_tools.get_upstream_lineage,
    ),
    Tool(
        name="lineage.downstream",
        description=(
            "Retrieve what depends on the resolved object "
            "(bounded-depth downstream lineage)."
        ),
        requires_context=frozenset({"semantic_model", "resolved_object"}),
        handler=lineage_tools.get_downstream_lineage,
    ),
    Tool(
        name="impact.analyze",
        description=(
            "Analyze downstream impact of the resolved object via the real "
            "impact graph."
        ),
        requires_context=frozenset({"semantic_model", "resolved_object"}),
        handler=impact_tools.analyze_impact,
    ),
)

TOOL_REGISTRY: dict[str, Tool] = {tool.name: tool for tool in _TOOLS}
