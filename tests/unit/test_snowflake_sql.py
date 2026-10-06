import pytest

from app.domain.snowflake_sql import (
    SqlColumnSource,
    SqlObjectName,
    describe_statement,
    extract_column_transformation,
    referenced_tables,
    split_identifier,
    table_column_type,
)


def _sources(result) -> list[tuple[str, str]]:
    return [
        (".".join(source.table.parts), source.column)
        for source in result.source_columns
    ]


@pytest.mark.parametrize(
    ("sql", "column", "expression", "kind", "sources"),
    [
        # GET_DDL style: lower-case, generated column list mapped by position.
        (
            "create or replace view DB.S.V(NET, ID) as\n"
            "select o.amount * 0.9, o.id from DB.CORE.ORDERS o",
            "NET",
            "o.amount * 0.9",
            "EXPRESSION",
            [("DB.CORE.ORDERS", "AMOUNT")],
        ),
        (
            "create view V as select CASE WHEN a > 1 THEN 'x, y' ELSE 'AS z' END "
            "AS label, b from T",
            "LABEL",
            "CASE WHEN a > 1 THEN 'x, y' ELSE 'AS z' END",
            "EXPRESSION",
            [("T", "A")],
        ),
        (
            "create view V as select cast(price as number(10,2)) price_2dp from T",
            "PRICE_2DP",
            "cast(price as number(10,2))",
            "EXPRESSION",
            [("T", "PRICE")],
        ),
        (
            'create view V as select t."Net Amount" as "Net" from T t',
            "Net",
            't."Net Amount"',
            "PASS_THROUGH",
            [("T", "Net Amount")],
        ),
        (
            "create view V as select v:customer.name::string as customer_name "
            "from RAW.EVENTS",
            "CUSTOMER_NAME",
            "v:customer.name::string",
            "EXPRESSION",
            [("RAW.EVENTS", "V")],
        ),
        (
            "create view V as select dateadd(day, 1, order_date) as next_day, "
            "extract(year from order_date) as yr, trim(both ' ' from name) as nm "
            "from T",
            "NEXT_DAY",
            "dateadd(day, 1, order_date)",
            "EXPRESSION",
            [("T", "ORDER_DATE")],
        ),
        (
            "create view V as select sum(amount) over (partition by region, "
            "segment order by day) as running from T",
            "RUNNING",
            "sum(amount) over (partition by region, segment order by day)",
            "EXPRESSION",
            [("T", "AMOUNT"), ("T", "REGION"), ("T", "SEGMENT"), ("T", "DAY")],
        ),
        # A dbt-style CTE chain: the final select only passes the column on.
        (
            "create or replace transient table DB.MART.F as (\n"
            "  with orders as (select id, gross - discount as net from DB.RAW.O),\n"
            "  final as (select o.net as net_sales from orders o)\n"
            "  select * from final\n)",
            "NET_SALES",
            "gross - discount",
            "EXPRESSION",
            [("DB.RAW.O", "GROSS"), ("DB.RAW.O", "DISCOUNT")],
        ),
        (
            "select x.total from (select a + b as total from T) x",
            "TOTAL",
            "a + b",
            "EXPRESSION",
            [("T", "A"), ("T", "B")],
        ),
        (
            "insert into DB.CORE.ORDERS (ID, AMOUNT)\n"
            "select r.id, r.amt::NUMBER(10,2) from RAW.R r",
            "AMOUNT",
            "r.amt::NUMBER(10,2)",
            "EXPRESSION",
            [("RAW.R", "AMT")],
        ),
        (
            "insert overwrite into T select a, b * 2 as doubled from S",
            "DOUBLED",
            "b * 2",
            "EXPRESSION",
            [("S", "B")],
        ),
        (
            "select a as x from T1 union all select b from T2",
            "X",
            "a UNION ALL b",
            "PASS_THROUGH",
            [("T1", "A"), ("T2", "B")],
        ),
        (
            "select a * 2 as x, x + 1 as y from T",
            "Y",
            "x + 1",
            "EXPRESSION",
            [("T", "A")],
        ),
        (
            "select f.value::string as tag from T, lateral flatten(input => t.tags) f",
            "TAG",
            "f.value::string",
            "EXPRESSION",
            [],
        ),
    ],
)
def test_column_expressions(sql, column, expression, kind, sources):
    result = extract_column_transformation(sql, column)

    assert result is not None
    assert result.expression == expression
    assert result.kind == kind
    assert _sources(result) == sources


def test_an_insert_without_a_column_list_maps_by_the_tables_column_order():
    result = extract_column_transformation(
        "insert into T select s.a, s.b + 1 from S s",
        "Y",
        table_columns=["X", "Y"],
    )

    assert result.expression == "s.b + 1"


def test_merge_reports_each_branch_that_sets_the_column():
    result = extract_column_transformation(
        "merge into DB.CORE.T t using (select id, amt from DB.RAW.S) s on t.id = s.id "
        "when matched then update set t.amount = s.amt * 2 "
        "when not matched then insert (id, amount) values (s.id, s.amt)",
        "AMOUNT",
    )

    assert result.expression == "WHEN MATCHED: s.amt * 2; WHEN NOT MATCHED: s.amt"
    assert result.branch_count == 2
    assert ("DB.RAW.S", "AMT") in _sources(result)


def test_update_from_resolves_through_the_from_clause():
    result = extract_column_transformation(
        "update T set total = s.price * s.qty from S s where T.id = s.id",
        "TOTAL",
    )

    assert result.expression == "s.price * s.qty"
    assert _sources(result) == [("S", "PRICE"), ("S", "QTY")]


def test_copy_from_a_stage():
    plain = extract_column_transformation("copy into T from @raw.stage/x/", "A")
    transformed = extract_column_transformation(
        "copy into T (A, B) from (select $1:a::string, $2 from @raw.stage s)", "A"
    )

    assert plain.kind == "STAGE_LOAD"
    assert plain.stage == "@raw.stage/x/"
    assert transformed.expression == "$1:a::string"
    assert transformed.stage == "@raw.stage"


def test_clone_and_external_and_dynamic_tables():
    clone = extract_column_transformation("create table T clone DB.S.SRC", "A")
    external = extract_column_transformation(
        "create or replace external table E (A varchar as (value:c1::varchar), "
        "B number as (value:c2::number)) location=@s file_format=(type=csv)",
        "B",
    )
    dynamic = extract_column_transformation(
        "create or replace dynamic table D target_lag = '1 minute' warehouse = WH "
        "as select a + 1 as a1 from T",
        "A1",
    )

    assert clone.kind == "CLONE"
    assert _sources(clone) == [("DB.S.SRC", "A")]
    assert external.expression == "value:c2::number"
    assert dynamic.expression == "a + 1"


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "select",
        "select 'unterminated from T",
        "create view V as select /* unterminated",
        "(" * 500 + "select a from T" + ")" * 500,
        "garbage %%% ;;; ((",
        "select a from T where " + "x and " * 50_000 + "1",
    ],
    ids=["empty", "bare", "quote", "comment", "nested", "garbage", "huge"],
)
def test_malformed_sql_never_raises(sql):
    extract_column_transformation(sql, "A")
    describe_statement(sql)
    referenced_tables(sql)


def test_a_column_the_statement_does_not_produce_is_none():
    assert extract_column_transformation("select a from T", "B") is None
    assert extract_column_transformation("insert into T values (1, 2)", "A") is None


def test_describe_statement_finds_targets_and_kinds():
    assert describe_statement(
        "INSERT INTO db.core.orders (id) SELECT 1"
    ) == describe_statement("insert into DB.CORE.ORDERS (ID) select 1")
    info = describe_statement(
        'create or replace secure view if not exists "My Db".s.V(A, B) as select 1, 2'
    )
    assert info.kind == "CREATE_VIEW"
    assert info.target == SqlObjectName(("My Db", "S", "V"))
    assert info.target_columns == ("A", "B")
    assert describe_statement("copy into @stage from T").kind == "OTHER"
    assert describe_statement("create table T (a int)").kind == "CREATE_TABLE"
    assert describe_statement("merge into T using S on 1=1").kind == "MERGE"


def test_referenced_tables_skip_cte_names_and_the_target():
    tables = referenced_tables(
        "insert into DB.MART.F with a as (select * from RAW.X) "
        "select * from a join DB.CORE.Y y on true"
    )

    # In FROM order: the CTE `a` reads RAW.X, then Y is joined.
    assert [".".join(name.parts) for name in tables] == ["RAW.X", "DB.CORE.Y"]


def test_identifiers_and_types():
    assert split_identifier('"My Db".sch."T.x"') == ("My Db", "SCH", "T.x")
    assert SqlObjectName(("CORE", "T")).resolve("DB", "S") == ("DB", "CORE", "T")
    assert (
        table_column_type(
            "create or replace TABLE T (ID NUMBER(38,0) NOT NULL, NAME VARCHAR(10))",
            "ID",
        )
        == "NUMBER(38,0)"
    )
    assert SqlColumnSource(SqlObjectName(("T",)), "A").certain is True
