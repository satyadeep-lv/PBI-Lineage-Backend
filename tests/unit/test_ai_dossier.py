"""The 360-degree evidence behind "explain X" and "explain this report"."""

from app.ai.composition.deterministic_renderer import DeterministicAnswerRenderer
from app.ai.context.semantic_objects import find_semantic_object
from app.ai.models.context import ResolvedAIContext, ResolvedReport
from app.ai.models.enums import AIAnswerStatus, AudienceType
from app.ai.models.evidence import EvidenceBundle
from app.ai.tools.dossier_tools import model_dossier, object_dossier, report_dossier
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
    NormalizedReportPage,
    NormalizedReportVisual,
    VisualFieldReference,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelPartition,
    ParsedSemanticModelRelationship,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)

WORKSPACE = "ws-poc"
MODEL = "model-sales"

_SNOWFLAKE_M = (
    'let Source = Snowflake.Databases("acct.snowflakecomputing.com", "COMPUTE_WH"),'
    ' Db = Source{[Name="PBI_DB",Kind="Database"]}[Data],'
    ' Schema = Db{[Name="MART",Kind="Schema"]}[Data],'
    ' View = Schema{[Name="V_ORDERS",Kind="View"]}[Data] in View'
)


def _model() -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id=WORKSPACE,
        semantic_model_id=MODEL,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="Orders",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Orders", mode="import", expression=_SNOWFLAKE_M
                    )
                ],
                columns=[
                    ParsedSemanticModelColumn(
                        name="Revenue", data_type="decimal", source_column="REVENUE"
                    ),
                    ParsedSemanticModelColumn(
                        name="Cost", data_type="decimal", source_column="COST"
                    ),
                    ParsedSemanticModelColumn(
                        name="CustomerKey", data_type="int64", source_column="CUST_ID"
                    ),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Total Revenue",
                        expression="SUM(Orders[Revenue])",
                        format_string="#,0",
                    ),
                    ParsedSemanticModelMeasure(
                        name="Total Cost", expression="SUM(Orders[Cost])"
                    ),
                    ParsedSemanticModelMeasure(
                        name="Profit Margin %",
                        expression=(
                            "DIVIDE([Total Revenue] - [Total Cost], [Total Revenue])"
                        ),
                    ),
                ],
            ),
            ParsedSemanticModelTable(
                name="Customer",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Customer",
                        expression=_SNOWFLAKE_M.replace("V_ORDERS", "DIM_CUSTOMER"),
                    )
                ],
                columns=[
                    ParsedSemanticModelColumn(
                        name="CustomerKey", data_type="int64", source_column="CUST_ID"
                    ),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Revenue per Customer",
                        expression=(
                            "DIVIDE([Total Revenue], "
                            "DISTINCTCOUNT(Customer[CustomerKey]))"
                        ),
                    ),
                ],
            ),
        ],
        relationships=[
            ParsedSemanticModelRelationship(
                name="orders_customer",
                from_table="Orders",
                from_column="CustomerKey",
                to_table="Customer",
                to_column="CustomerKey",
                is_active=True,
                cardinality="manyToOne",
            )
        ],
    )


def _report(report_id: str, visuals: list[tuple[str, str, str, str]]):
    return NormalizedReportDefinitionResponse(
        workspace_id=WORKSPACE,
        report_id=report_id,
        format="PBIR",
        pages=[
            NormalizedReportPage(
                name="p1",
                display_name="Overview",
                visuals=[
                    NormalizedReportVisual(
                        id=f"{report_id}-{title}",
                        internal_name=title,
                        title=title,
                        visual_type=visual_type,
                        field_references=[
                            VisualFieldReference(
                                object_type=kind,
                                table_name="Orders"
                                if kind == "measure"
                                else "Customer",
                                object_name=field,
                                usage="projection",
                            )
                        ],
                    )
                    for title, visual_type, kind, field in visuals
                ],
                visual_count=len(visuals),
            )
        ],
        page_count=1,
        visual_count=len(visuals),
        source_part_count=1,
        decoded_json_part_count=1,
        warnings=[],
    )


def _context(object_name: str | None = None) -> ResolvedAIContext:
    model = _model()
    return ResolvedAIContext(
        workspace_id=WORKSPACE,
        workspace_name="POC",
        report_id="r-main",
        report_name="check_remane_app",
        semantic_model_id=MODEL,
        semantic_model_name="sales",
        semantic_model_workspace_id=WORKSPACE,
        semantic_model_workspace_name="POC",
        parsed_semantic_model=model,
        report_definition=_report(
            "r-main",
            [
                ("Margin Card", "card", "measure", "Profit Margin %"),
                ("Revenue KPI", "kpi", "measure", "Total Revenue"),
            ],
        ),
        related_reports=[
            ResolvedReport(
                workspace_id="ws-dev",
                workspace_name="DEV",
                report_id="r-other",
                report_name="Finance Pack",
                definition=_report(
                    "r-other",
                    [("Cost Table", "table", "measure", "Total Cost")],
                ),
            )
        ],
        resolved_object=(
            find_semantic_object(model, object_name) if object_name else None
        ),
    )


def _by(items, fact_type, object_type=None):
    return [
        item
        for item in items
        if item.fact_type == fact_type
        and (object_type is None or item.object_type == object_type)
    ]


def test_a_measure_dossier_covers_every_layer():
    items = object_dossier(_context("Total Revenue"))

    context = _by(items, "relationship", "context")[0]
    assert "semantic model 'sales'" in context.display_value
    assert "workspace 'POC'" in context.display_value

    definition = _by(items, "definition")[0]
    assert definition.value == "SUM(Orders[Revenue])"
    assert definition.plain_language
    assert "format #,0" in definition.display_value

    # Semantic lineage: the column it reads.
    assert {item.object_name for item in _by(items, "dependency")} == {"Revenue"}

    # Database lineage: the Snowflake view and the physical column behind it.
    source = _by(items, "source")[0]
    assert source.value["database"] == "PBI_DB"
    assert source.value["schema_name"] == "MART"
    assert source.value["object_name"] == "V_ORDERS"
    assert source.value["columns"] == ["REVENUE"]
    assert "Snowflake view PBI_DB.MART.V_ORDERS" in source.display_value

    # What is built on it, in its own table and in another one.
    dependents = {item.object_name for item in _by(items, "impact", "measure")}
    assert dependents == {"Profit Margin %", "Revenue per Customer"}
    tables = {item.object_name for item in _by(items, "impact", "semantic_table")}
    assert tables == {"Orders", "Customer"}


def test_visual_impact_spans_every_report_on_the_model():
    items = object_dossier(_context("Total Revenue"))

    visuals = {item.object_name: item for item in _by(items, "impact", "visual")}
    # Directly, and through a dependent measure.
    assert visuals["Revenue KPI"].value["direct"] is True
    assert visuals["Margin Card"].value["direct"] is False
    assert visuals["Margin Card"].value["via"] == ["Profit Margin %"]
    assert "Report 'check_remane_app' > page 'Overview'" in (
        visuals["Margin Card"].display_value
    )
    # A visual that uses an unrelated measure is not impacted.
    assert "Cost Table" not in visuals

    coverage = " ".join(
        item.display_value for item in _by(items, "relationship", "coverage")
    )
    assert "checked in 2 reports" in coverage


def test_a_report_on_another_workspace_is_checked_too():
    items = object_dossier(_context("Total Cost"))

    visuals = {item.object_name: item for item in _by(items, "impact", "visual")}
    assert visuals["Cost Table"].value["report"] == "Finance Pack"
    assert visuals["Cost Table"].value["workspace"] == "DEV"
    assert visuals["Margin Card"].value["via"] == ["Profit Margin %"]


def test_a_column_dossier_reaches_measures_and_visuals_downstream():
    items = object_dossier(_context("Orders[Cost]"))

    definition = _by(items, "definition")[0]
    assert definition.object_type == "column"
    assert "loaded from source column COST" in definition.display_value
    assert _by(items, "source")[0].value["columns"] == ["COST"]
    assert {item.object_name for item in _by(items, "impact", "measure")} == {
        "Total Cost",
        "Profit Margin %",
    }
    assert {item.object_name for item in _by(items, "impact", "visual")} == {
        "Margin Card",
        "Cost Table",
    }


def test_a_table_dossier_names_its_source_and_everything_reading_it():
    items = object_dossier(_context("Customer"))

    definition = _by(items, "definition")[0]
    assert definition.object_type == "table"
    assert "(Revenue per Customer)" in definition.display_value
    source = _by(items, "source")[0]
    assert source.value["object_name"] == "DIM_CUSTOMER"
    assert source.value["columns"] == ["CUST_ID"]
    # Its own measure reads Orders through Total Revenue: that is upstream of
    # the table, not something the table's change would break.
    assert "Total Revenue" in {item.object_name for item in _by(items, "dependency")}


def test_the_report_dossier_answers_the_suggested_questions():
    items = report_dossier(_context())

    summary = _by(items, "definition", "report")[0]
    # "Which semantic model powers it?"
    assert "built on semantic model 'sales'" in summary.display_value

    # "Which measures are used?" -- with their DAX and the visuals using them.
    used = {
        item.object_name: item
        for item in _by(items, "usage")
        if item.object_type in ("measure", "column")
    }
    assert set(used) == {"Profit Margin %", "Total Revenue"}
    assert used["Total Revenue"].value["expression"] == "SUM(Orders[Revenue])"
    assert "'Revenue KPI' (kpi) on 'Overview'" in used["Total Revenue"].display_value

    # "Where does the data come from?" -- through the measures, to Snowflake.
    source = _by(items, "source")[0]
    assert source.value["object_name"] == "V_ORDERS"
    assert set(source.value["columns"]) == {"REVENUE", "COST"}


def test_the_model_dossier_lists_tables_relationships_and_reports():
    items = model_dossier(_context())

    tables = {
        item.object_name: item for item in _by(items, "relationship", "semantic_table")
    }
    assert "Snowflake view PBI_DB.MART.V_ORDERS" in tables["Orders"].display_value
    assert "import mode" in tables["Orders"].display_value

    relationship = _by(items, "relationship", "relationship")[0]
    assert relationship.display_value.startswith(
        "Orders[CustomerKey] -> Customer[CustomerKey]"
    )

    measures = {item.object_name for item in _by(items, "definition", "measure")}
    assert "Profit Margin %" in measures
    reports = {item.object_name for item in _by(items, "usage", "report")}
    assert reports == {"check_remane_app", "Finance Pack"}


def test_without_a_report_the_dossier_says_visuals_were_not_checked():
    context = _context("Total Revenue").model_copy(
        update={"report_definition": None, "related_reports": []}
    )

    items = object_dossier(context)

    assert not _by(items, "impact", "visual")
    coverage = [item.display_value for item in _by(items, "relationship", "coverage")]
    assert any("visual impact could not be checked" in note for note in coverage)


def test_the_deterministic_answer_reads_as_sections_not_a_dump():
    items = object_dossier(_context("Profit Margin %"))
    bundle = EvidenceBundle(
        question="Explain Profit Margin %",
        context=_context("Profit Margin %"),
        evidence=items,
        can_answer=True,
        status=AIAnswerStatus.ANSWERED,
    )

    answer = DeterministicAnswerRenderer.render(bundle, AudienceType.BUSINESS)

    assert answer.startswith("Profit Margin % is a measure in table Orders")
    for title in (
        "In plain English",
        "Definition",
        "Depends on (semantic model lineage)",
        "Reads from (database lineage)",
        "Visual impact",
    ):
        assert f"\n\n{title}\n" in answer
    # DAX indented on its own line, verbatim.
    assert "\n    DIVIDE([Total Revenue] - [Total Cost], [Total Revenue])" in answer
    # Plain text for a panel that does not render Markdown.
    assert "**" not in answer and "{" not in answer
