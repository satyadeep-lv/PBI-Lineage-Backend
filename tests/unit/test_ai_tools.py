from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.tools import impact_tools, lineage_tools, measure_tools, report_tools
from tests.unit.ai_fixtures import (
    GROSS_MARGIN_DAX,
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_report_definition,
    sample_semantic_model,
)


def _measure_context(**overrides) -> ResolvedAIContext:
    defaults = dict(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        parsed_semantic_model=sample_semantic_model(),
        resolved_object=ResolvedObject(
            object_type="measure",
            table_name="Sales",
            object_name="Gross Margin %",
            qualified_name="Sales[Gross Margin %]",
        ),
    )
    defaults.update(overrides)
    return ResolvedAIContext(**defaults)


def test_get_measure_definition_returns_exact_dax():
    items = measure_tools.get_measure_definition(_measure_context())

    assert len(items) == 1
    assert items[0].value == GROSS_MARGIN_DAX
    assert items[0].verification_status == "verified"
    assert items[0].source_reference == "definition/tables/Sales.tmdl"


def test_get_measure_definition_empty_without_resolved_object():
    context = ResolvedAIContext(parsed_semantic_model=sample_semantic_model())

    assert measure_tools.get_measure_definition(context) == []


def test_get_measure_definition_empty_for_unknown_measure():
    context = _measure_context(
        resolved_object=ResolvedObject(
            object_type="measure",
            table_name="Sales",
            object_name="Does Not Exist",
            qualified_name="Sales[Does Not Exist]",
        )
    )

    assert measure_tools.get_measure_definition(context) == []


def test_get_upstream_lineage_reaches_dependencies_and_physical_source():
    items = lineage_tools.get_upstream_lineage(_measure_context())

    object_names = {item.object_name for item in items}
    object_types = {item.object_type for item in items}

    assert "Gross Profit" in object_names
    assert "Net Sales" in object_names
    assert "physical_source" in object_types

    # Semantic-model objects and the database behind them are different kinds
    # of answer, so they are reported as separate fact types rather than one
    # flat "depends on" list.
    fact_types = {item.object_type: item.fact_type for item in items}
    assert fact_types["physical_source"] == "source"
    assert fact_types["semantic_measure"] == "dependency"
    assert all(
        item.fact_type == "dependency"
        for item in items
        if item.object_type != "physical_source"
    )

    # The database detail travels with it, so a caller need not parse the
    # qualified name back apart.
    source = next(item for item in items if item.object_type == "physical_source")
    assert source.value["properties"]["provider"]


def test_get_downstream_lineage_empty_when_nothing_downstream():
    # "Gross Margin %" has no report lineage in this context, so nothing
    # references it further downstream.
    items = lineage_tools.get_downstream_lineage(_measure_context())

    assert items == []


def test_analyze_impact_reaches_visual_via_report_lineage():
    context = _measure_context(report_definition=sample_report_definition())

    items = impact_tools.analyze_impact(context)

    visual_items = [item for item in items if item.object_type == "visual"]
    assert len(visual_items) == 1
    assert visual_items[0].value["distance"] == 1
    assert visual_items[0].fact_type == "impact"


def test_tools_return_no_invented_facts_when_context_is_empty():
    empty_context = ResolvedAIContext()

    assert measure_tools.get_measure_definition(empty_context) == []
    assert lineage_tools.get_upstream_lineage(empty_context) == []
    assert lineage_tools.get_downstream_lineage(empty_context) == []
    assert impact_tools.analyze_impact(empty_context) == []
    assert lineage_tools.get_semantic_model_details(empty_context) == []
    assert lineage_tools.get_physical_sources(empty_context) == []
    assert report_tools.get_report_summary(empty_context) == []
    assert report_tools.get_report_pages(empty_context) == []
    assert report_tools.get_report_visuals(empty_context) == []


def test_get_semantic_model_details_counts():
    context = ResolvedAIContext(parsed_semantic_model=sample_semantic_model())

    items = lineage_tools.get_semantic_model_details(context)

    assert len(items) == 1
    assert items[0].value["table_count"] == 1
    assert items[0].value["measure_count"] == 3
    assert items[0].value["column_count"] == 2


def test_get_physical_sources_from_power_query():
    context = ResolvedAIContext(parsed_semantic_model=sample_semantic_model())

    items = lineage_tools.get_physical_sources(context)

    assert len(items) == 1
    assert items[0].object_name == "FactSales"
    assert items[0].fact_type == "source"


def test_get_report_summary_and_pages_and_visuals():
    context = ResolvedAIContext(report_definition=sample_report_definition())

    summary = report_tools.get_report_summary(context)
    pages = report_tools.get_report_pages(context)
    visuals = report_tools.get_report_visuals(context)

    assert summary[0].value["page_count"] == 1
    assert summary[0].value["visual_count"] == 1
    assert pages[0].object_name == "Overview"
    assert visuals[0].object_name == "Margin Card"
    assert visuals[0].value["fields"][0]["object_name"] == "Gross Margin %"
