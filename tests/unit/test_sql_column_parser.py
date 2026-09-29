from app.services.sql_column_parser import parse_select_columns, split_dotted_identifier


def test_parses_aliased_and_bare_dotted_columns():
    columns = parse_select_columns(
        "SELECT t.SalesAmount AS Amount, t.OrderDate FROM dbo.Sales t"
    )

    assert [(c.output_name, c.source_identifiers) for c in columns] == [
        ("Amount", ["SalesAmount"]),
        ("OrderDate", ["OrderDate"]),
    ]


def test_skips_star_projection():
    assert parse_select_columns("SELECT * FROM dbo.Sales") == []
    assert parse_select_columns("SELECT s.* FROM dbo.Sales s") == []


def test_resolves_implicit_alias_without_as_keyword():
    columns = parse_select_columns(
        "SELECT DISTINCT EMPLOYEE_ID, GROSS_PAY + NET_PAY TOTAL_PAY FROM Payroll"
    )

    assert [(c.output_name, c.source_identifiers) for c in columns] == [
        ("EMPLOYEE_ID", ["EMPLOYEE_ID"]),
        ("TOTAL_PAY", ["GROSS_PAY", "NET_PAY"]),
    ]


def test_computed_expression_returns_every_referenced_column():
    columns = parse_select_columns(
        "SELECT FIRST_NAME || ' ' || LAST_NAME AS FULL_NAME FROM dbo.Employee"
    )

    assert columns[0].output_name == "FULL_NAME"
    assert columns[0].source_identifiers == ["FIRST_NAME", "LAST_NAME"]


def test_implicit_alias_for_plain_qualified_column():
    columns = parse_select_columns("SELECT s.SalesAmount Amount FROM dbo.Sales s")

    assert columns[0].output_name == "Amount"
    assert columns[0].source_identifiers == ["SalesAmount"]


def test_alias_after_nested_cast_uses_outer_as_keyword():
    columns = parse_select_columns(
        "SELECT CAST(t.Amount AS DECIMAL(10,2)) AS Amount2 FROM dbo.Sales t"
    )

    assert len(columns) == 1
    assert columns[0].output_name == "Amount2"
    assert columns[0].source_identifiers == ["Amount"]
    assert columns[0].raw_expression == "CAST(t.Amount AS DECIMAL(10,2))"


def test_bracketed_and_quoted_identifiers_are_unquoted():
    columns = parse_select_columns(
        'SELECT [dbo].[Sales].[Sales Amount] AS "Amount" FROM dbo.Sales'
    )

    assert columns[0].output_name == "Amount"
    assert columns[0].source_identifiers == ["Sales Amount"]


def test_function_names_are_not_treated_as_columns():
    columns = parse_select_columns("SELECT SUM(t.Amount) AS Total FROM dbo.Sales t")

    assert columns[0].source_identifiers == ["Amount"]


def test_string_literal_column_falls_back_to_alias_name():
    columns = parse_select_columns("SELECT 'Retail' AS Channel FROM dbo.Sales")

    assert columns[0].output_name == "Channel"
    assert columns[0].source_identifiers == ["Channel"]


def test_returns_empty_list_without_select_from():
    assert parse_select_columns("EXEC dbo.GetSales") == []


def test_split_dotted_identifier_handles_quoting_and_brackets():
    assert split_dotted_identifier("dbo.Sales") == ["dbo", "Sales"]
    assert split_dotted_identifier("[My Db].[dbo].[Sales]") == [
        "My Db",
        "dbo",
        "Sales",
    ]
    assert split_dotted_identifier('"warehouse"."dbo"."Sales"') == [
        "warehouse",
        "dbo",
        "Sales",
    ]
