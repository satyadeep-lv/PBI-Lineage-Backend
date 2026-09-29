from app.domain.dax_lineage import terminal_dependencies
from app.schemas.xmla_metadata import (
    XmlaCalcDependency,
    XmlaSemanticModelColumn,
    XmlaSemanticModelMeasure,
    XmlaSemanticModelMetadataResponse,
    XmlaSemanticModelPartition,
    XmlaSemanticModelTable,
)
from app.services.xmla_column_lineage_adapter import (
    build_dax_dependency_analysis,
    build_parsed_semantic_model,
)


def _metadata() -> XmlaSemanticModelMetadataResponse:
    return XmlaSemanticModelMetadataResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        xmla_endpoint="powerbi://api.powerbi.com/v1.0/myorg/Sales",
        table_count=2,
        column_count=2,
        measure_count=2,
        relationship_count=0,
        hierarchy_count=0,
        partition_count=2,
        tables=[
            XmlaSemanticModelTable(
                name="Sales",
                columns=[
                    XmlaSemanticModelColumn(name="Amount", source_column="Amount"),
                    XmlaSemanticModelColumn(
                        name="OrderDate", source_column="OrderDate"
                    ),
                ],
                measures=[
                    XmlaSemanticModelMeasure(
                        name="Total Sales",
                        expression="SUM(Sales[Amount])",
                    ),
                    XmlaSemanticModelMeasure(
                        name="Sales With Tax",
                        expression="[Total Sales] * 1.2",
                    ),
                ],
                partitions=[
                    XmlaSemanticModelPartition(
                        name="Sales",
                        mode="Import",
                        source_type="M",
                        expression=(
                            'let Source = Sql.Database("sql.example.com", "warehouse"),'
                            " Result = Value.NativeQuery(Source,"
                            ' "SELECT s.SalesAmount AS Amount, s.OrderDate'
                            ' FROM dbo.Sales s") in Result'
                        ),
                    )
                ],
            ),
            XmlaSemanticModelTable(
                name="Dates",
                partitions=[
                    XmlaSemanticModelPartition(
                        name="Dates",
                        mode="Import",
                        source_type="Calculated",
                        expression="",
                    )
                ],
            ),
        ],
        calc_dependencies=[
            XmlaCalcDependency(
                object_type="MEASURE",
                table="Sales",
                object="Total Sales",
                expression="SUM(Sales[Amount])",
                referenced_object_type="COLUMN",
                referenced_table="Sales",
                referenced_object="Amount",
            ),
            XmlaCalcDependency(
                object_type="MEASURE",
                table="Sales",
                object="Sales With Tax",
                expression="[Total Sales] * 1.2",
                referenced_object_type="MEASURE",
                referenced_table="Sales",
                referenced_object="Total Sales",
            ),
            XmlaCalcDependency(
                object_type="CALC_TABLE",
                table="Dates",
                object="Dates",
                expression="CALENDAR(DATE(2015,1,1), DATE(2020,12,31))",
                referenced_object_type="COLUMN",
                referenced_table="Sales",
                referenced_object="OrderDate",
            ),
            XmlaCalcDependency(
                object_type="ACTIVE_RELATIONSHIP",
                table="Sales",
                object="",
                referenced_object_type="TABLE",
                referenced_table="Dates",
                referenced_object="Dates",
            ),
        ],
    )


def test_build_dax_dependency_analysis_covers_measures_and_calc_tables():
    result = build_dax_dependency_analysis(_metadata())

    edges = {
        (edge.source.qualified_name, edge.target.qualified_name)
        for edge in result.dependencies
    }

    assert ("Sales[Amount]", "Sales[Total Sales]") in edges
    assert ("Sales[Total Sales]", "Sales[Sales With Tax]") in edges
    assert ("Sales[OrderDate]", "Dates") in edges
    assert result.object_count == 3
    assert result.cycle_count == 0
    assert result.warnings == []


def test_dax_dependency_analysis_resolves_measure_type_for_intermediate_reference():
    result = build_dax_dependency_analysis(_metadata())

    sales_with_tax = next(
        obj for obj in result.objects if obj.qualified_name == "Sales[Sales With Tax]"
    )
    terminals = terminal_dependencies(sales_with_tax, result)

    assert [(t.qualified_name, depth) for t, depth in terminals] == [
        ("Sales[Amount]", 2),
    ]


def test_redundant_whole_table_dependency_is_dropped_when_column_is_known():
    metadata = XmlaSemanticModelMetadataResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        xmla_endpoint="powerbi://api.powerbi.com/v1.0/myorg/Sales",
        table_count=1,
        column_count=1,
        measure_count=1,
        relationship_count=0,
        hierarchy_count=0,
        partition_count=0,
        calc_dependencies=[
            XmlaCalcDependency(
                object_type="MEASURE",
                table="Sales",
                object="Total Sales",
                expression="SUM(Sales[Amount])",
                referenced_object_type="COLUMN",
                referenced_table="Sales",
                referenced_object="Amount",
            ),
            XmlaCalcDependency(
                object_type="MEASURE",
                table="Sales",
                object="Total Sales",
                expression="SUM(Sales[Amount])",
                referenced_object_type="TABLE",
                referenced_table="Sales",
                referenced_object="Sales",
            ),
        ],
    )

    result = build_dax_dependency_analysis(metadata)

    edges = [
        (edge.source.qualified_name, edge.source.object_type)
        for edge in result.dependencies
    ]

    assert edges == [("Sales[Amount]", "column")]


def test_redundant_whole_table_dependency_is_dropped_for_calculated_column_owner():
    """Auto date-table columns (Day/Month/Year) depend on a same-table
    column ([Date]) alongside a redundant whole-table self-reference; this
    must be filtered the same way as a measure's table-context dependency.
    """
    metadata = XmlaSemanticModelMetadataResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        xmla_endpoint="powerbi://api.powerbi.com/v1.0/myorg/Sales",
        table_count=1,
        column_count=2,
        measure_count=0,
        relationship_count=0,
        hierarchy_count=0,
        partition_count=0,
        calc_dependencies=[
            XmlaCalcDependency(
                object_type="CALC_COLUMN",
                table="DateTableTemplate_x",
                object="Day",
                expression="DAY([Date])",
                referenced_object_type="COLUMN",
                referenced_table="DateTableTemplate_x",
                referenced_object="Date",
            ),
            XmlaCalcDependency(
                object_type="CALC_COLUMN",
                table="DateTableTemplate_x",
                object="Day",
                expression="DAY([Date])",
                referenced_object_type="TABLE",
                referenced_table="DateTableTemplate_x",
                referenced_object="DateTableTemplate_x",
            ),
        ],
    )

    result = build_dax_dependency_analysis(metadata)

    edges = [
        (edge.source.qualified_name, edge.source.object_type)
        for edge in result.dependencies
    ]

    assert edges == [("DateTableTemplate_x[Date]", "column")]


def test_whole_table_dependency_is_kept_when_no_column_dependency_exists():
    metadata = XmlaSemanticModelMetadataResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        xmla_endpoint="powerbi://api.powerbi.com/v1.0/myorg/Sales",
        table_count=1,
        column_count=0,
        measure_count=1,
        relationship_count=0,
        hierarchy_count=0,
        partition_count=0,
        calc_dependencies=[
            XmlaCalcDependency(
                object_type="MEASURE",
                table="Sales",
                object="Row Count",
                expression="COUNTROWS(Sales)",
                referenced_object_type="TABLE",
                referenced_table="Sales",
                referenced_object="Sales",
            ),
        ],
    )

    result = build_dax_dependency_analysis(metadata)

    assert [
        (edge.source.qualified_name, edge.source.object_type)
        for edge in result.dependencies
    ] == [("Sales", "table")]


def test_build_parsed_semantic_model_marks_calc_table_and_keeps_native_query():
    model = build_parsed_semantic_model(_metadata())

    sales_table = next(table for table in model.tables if table.name == "Sales")
    dates_table = next(table for table in model.tables if table.name == "Dates")

    assert sales_table.expression is None
    assert sales_table.partitions[0].source_type != "calculated"
    assert "Value.NativeQuery" in (sales_table.partitions[0].expression or "")

    assert dates_table.expression == "CALENDAR(DATE(2015,1,1), DATE(2020,12,31))"
    assert dates_table.partitions[0].source_type == "calculated"
