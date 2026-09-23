import base64

from app.schemas.semantic_model_definition import (
    SemanticModelDefinition,
    SemanticModelDefinitionPart,
    SemanticModelDefinitionResponse,
)
from app.services.semantic_model_definition_parser import (
    SemanticModelDefinitionParser,
)


def _encode(
    text: str,
) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _raw_definition(
    *,
    text: str,
    definition_format: str = "TMDL",
    payload_type: str = "InlineBase64",
) -> SemanticModelDefinitionResponse:
    return SemanticModelDefinitionResponse(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        definition=SemanticModelDefinition(
            format=definition_format,
            parts=[
                SemanticModelDefinitionPart(
                    path="definition/tables/Sales.tmdl",
                    payload=_encode(text),
                    payload_type=payload_type,
                )
            ],
        ),
    )


def test_parse_tmdl_table():
    raw = _raw_definition(
        text="""
table Sales
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    assert result.workspace_id == "workspace-123"
    assert result.semantic_model_id == "model-123"
    assert result.format == "TMDL"
    assert len(result.tables) == 1
    assert result.tables[0].name == "Sales"
    assert result.tables[0].source_path == "definition/tables/Sales.tmdl"


def test_parse_tmdl_column():
    raw = _raw_definition(
        text="""
table Sales
    column Amount
        dataType: decimal
        sourceColumn: Amount
        isHidden: false
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    column = result.tables[0].columns[0]

    assert column.name == "Amount"
    assert column.data_type == "decimal"
    assert column.source_column == "Amount"
    assert column.is_hidden is False
    assert column.source_path == "definition/tables/Sales.tmdl"


def test_parse_tmdl_column_lineage_tags():
    raw = _raw_definition(
        text="""
table Employees
    column EmployeeId
        dataType: int64
        sourceColumn: EmployeeId
        lineageTag: 11111111-1111-1111-1111-111111111111
        sourceLineageTag: 22222222-2222-2222-2222-222222222222
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    column = result.tables[0].columns[0]

    assert column.lineage_tag == "11111111-1111-1111-1111-111111111111"
    assert column.source_lineage_tag == "22222222-2222-2222-2222-222222222222"


def test_parse_tmdl_entity_partition_and_shared_expression():
    # Fabric returns shared expressions as their own definition part, which
    # is the only context a top-level `expression` block appears in.
    table_text = """
table PAYROLL_RECORDS
    column TOTAL_PAY
        dataType: double

    partition PAYROLL_RECORDS = entity
        mode: directQuery
        source
            entityName: PAYROLL_RECORDS
            expressionSource: 'DirectQuery to AS - NativeQueryReoprt'
"""
    expression_text = """
expression 'DirectQuery to AS - NativeQueryReoprt' =
    let
      Source = AnalysisServices.Database("powerbi://myorg/DEV", "NativeQueryReoprt"),
      Cube = Cubes{[Id="Model", Kind="Cube"]}[Data]
    in
      Cube
    lineageTag: d9167c14-8ddc-418e-af71-12f4f5562009

    annotation PBI_IncludeFutureArtifacts = True
"""
    raw = SemanticModelDefinitionResponse(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        definition=SemanticModelDefinition(
            format="TMDL",
            parts=[
                SemanticModelDefinitionPart(
                    path="definition/tables/PAYROLL_RECORDS.tmdl",
                    payload=_encode(table_text),
                    payload_type="InlineBase64",
                ),
                SemanticModelDefinitionPart(
                    path="definition/expressions.tmdl",
                    payload=_encode(expression_text),
                    payload_type="InlineBase64",
                ),
            ],
        ),
    )

    result = SemanticModelDefinitionParser().parse(raw)

    partition = result.tables[0].partitions[0]
    assert partition.source_type == "entity"
    assert partition.entity_name == "PAYROLL_RECORDS"
    assert partition.expression_source == ("DirectQuery to AS - NativeQueryReoprt")

    expression = result.expressions[0]
    assert expression.name == "DirectQuery to AS - NativeQueryReoprt"
    assert expression.lineage_tag == "d9167c14-8ddc-418e-af71-12f4f5562009"
    # The `Source = ...` line looks like a property assignment but is the
    # part naming the upstream model, so it must survive verbatim.
    assert "AnalysisServices.Database" in (expression.expression or "")
    assert "myorg/DEV" in (expression.expression or "")
    assert "annotation" not in (expression.expression or "")
    assert "lineageTag" not in (expression.expression or "")


def test_parse_tmdl_measure():
    raw = _raw_definition(
        text="""
table Sales
    measure Total Sales = SUM(Sales[Amount])
        formatString: '$#,0.00'
        isHidden: false
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    measure = result.tables[0].measures[0]

    assert measure.name == "Total Sales"
    assert measure.expression == "SUM(Sales[Amount])"
    assert measure.format_string == "$#,0.00"
    assert measure.is_hidden is False
    assert measure.source_path == "definition/tables/Sales.tmdl"


def test_parse_tmdl_quoted_names_and_multiline_measure_expression():
    raw = _raw_definition(
        text="""
table 'Sales Data'
    column 'Order Amount'
        dataType = decimal
        sourceColumn = 'Order Amount'
        isHidden = true
    measure 'Total Sales' =
        SUMX(
            Sales,
            Sales[Amount]
        )
        formatString = '$#,0.00'
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    table = result.tables[0]
    column = table.columns[0]
    measure = table.measures[0]

    assert table.name == "Sales Data"
    assert column.name == "Order Amount"
    assert column.source_column == "Order Amount"
    assert column.is_hidden is True
    assert measure.name == "Total Sales"
    assert measure.expression == ("SUMX(\nSales,\nSales[Amount]\n)")
    assert measure.format_string == "$#,0.00"


def test_parse_tmdl_multiline_measure_ignores_unmapped_properties():
    raw = _raw_definition(
        text="""
table Sales
    measure Total Sales =
        VAR Total = SUM(Sales[Amount])
        RETURN Total
        displayFolder = Finance
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    measure = result.tables[0].measures[0]

    assert measure.expression == ("VAR Total = SUM(Sales[Amount])\nRETURN Total")


def test_parse_tmdl_relationship():
    raw = _raw_definition(
        text="""
relationship SalesCustomer
    fromColumn: Sales[CustomerId]
    toColumn: Customer[CustomerId]
    isActive: true
    cardinality: manyToOne
    crossFilteringBehavior: bothDirections
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    relationship = result.relationships[0]

    assert relationship.name == "SalesCustomer"
    assert relationship.from_table == "Sales"
    assert relationship.from_column == "CustomerId"
    assert relationship.to_table == "Customer"
    assert relationship.to_column == "CustomerId"
    assert relationship.is_active is True
    assert relationship.cardinality == "manyToOne"
    assert relationship.cross_filter_direction == "bothDirections"
    assert relationship.source_path == "definition/tables/Sales.tmdl"


def test_parse_tmdl_relationship_dot_references():
    raw = _raw_definition(
        text="""
relationship SalesCustomer
    fromColumn: 'Sales Data'.'Customer Id'
    toColumn: Customer.CustomerId
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    relationship = result.relationships[0]
    assert relationship.from_table == "Sales Data"
    assert relationship.from_column == "Customer Id"
    assert relationship.to_table == "Customer"
    assert relationship.to_column == "CustomerId"


def test_parse_tmdl_auto_date_time_variation_does_not_truncate_table():
    # Every column with Auto Date/Time enabled (the Power BI Desktop default) gets a
    # `variation` block whose `relationship:` property line starts with the literal
    # string "relationship" -- this must never be mistaken for a new top-level
    # `relationship <name>` block, which would reset the parser's current table and
    # silently drop everything declared afterward in the same file.
    raw = _raw_definition(
        text="""
table 'Sales Story'
    column ORDER_DATE
        dataType: dateTime
        variation Variation
            isDefault
            relationship: 95cf999c-ba78-491f-bfd9-d8ced9e0fe4b
            defaultHierarchy: LocalDateTable_ae43a320.'Date Hierarchy'
    column NET_SALES
        dataType: double
    measure 'Total Revenue' = SUM('Sales Story'[NET_SALES])
    hierarchy 'Customer Hierarchy'
        level Region
            column: REGION
    partition 'Sales Story' = m
        mode: import
        source = let X = 1 in X
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    table = result.tables[0]
    assert [column.name for column in table.columns] == ["ORDER_DATE", "NET_SALES"]
    assert [measure.name for measure in table.measures] == ["Total Revenue"]
    assert [hierarchy.name for hierarchy in table.hierarchies] == ["Customer Hierarchy"]
    assert [partition.name for partition in table.partitions] == ["Sales Story"]
    assert result.relationships == []


def test_parse_tmdl_power_query_partition():
    raw = _raw_definition(
        text="""
table Sales
    partition Sales = m
        mode: import
        source =
            let
                Source = Sql.Database("sql.example.com", "warehouse"),
                Orders = Source{[Schema="dbo",Item="Sales"]}[Data]
            in
                Orders
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    partition = result.tables[0].partitions[0]

    assert partition.name == "Sales"
    assert partition.mode == "import"
    assert partition.source_type == "m"
    assert partition.expression == (
        "let\n"
        'Source = Sql.Database("sql.example.com", "warehouse"),\n'
        'Orders = Source{[Schema="dbo",Item="Sales"]}[Data]\n'
        "in\n"
        "Orders"
    )
    assert partition.source_path == "definition/tables/Sales.tmdl"


def test_parse_tmdl_calculated_column_and_table_partition_dax():
    raw = _raw_definition(
        text="""
table Sales
    column Amount

table Summary
    column DoubleAmount = Sales[Amount] * 2
    partition Summary = calculated
        mode: import
        source =
            SUMMARIZE(
                Sales,
                Sales[Amount]
            )
"""
    )

    result = SemanticModelDefinitionParser().parse(raw)

    summary = result.tables[1]
    assert summary.columns[0].name == "DoubleAmount"
    assert summary.columns[0].expression == "Sales[Amount] * 2"
    assert summary.partitions[0].source_type == "calculated"
    assert summary.expression == ("SUMMARIZE(\nSales,\nSales[Amount]\n)")


def test_invalid_base64_adds_warning():
    raw = SemanticModelDefinitionResponse(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        definition=SemanticModelDefinition(
            format="TMDL",
            parts=[
                SemanticModelDefinitionPart(
                    path="definition/tables/Sales.tmdl",
                    payload="not-valid-base64",
                    payload_type="InlineBase64",
                )
            ],
        ),
    )

    result = SemanticModelDefinitionParser().parse(raw)

    assert result.tables == []
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "INVALID_BASE64_PAYLOAD"
    assert result.warnings[0].path == "definition/tables/Sales.tmdl"


def test_tmsl_returns_unsupported_warning():
    raw = _raw_definition(
        text="{}",
        definition_format="TMSL",
    )

    result = SemanticModelDefinitionParser().parse(raw)

    assert result.tables == []
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "UNSUPPORTED_FORMAT"
