from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.clients.snowflake_metadata_client import (
    SnowflakeMetadataClient,
    contains_pattern,
    qualified_identifier,
    quote_identifier,
)
from app.core.exceptions import UpstreamRequestError


class _Cursor:
    def __init__(self, description, rows, error=None) -> None:
        self.description = description
        self.rows = rows
        self.error = error
        self.executed: list[tuple[str, object, object]] = []
        self.closed = False

    def execute(self, sql, parameters=None, timeout=None):
        self.executed.append((sql, parameters, timeout))
        if self.error is not None:
            raise self.error

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.query_cursor = cursor

    def cursor(self):
        return self.query_cursor


def _connection(columns, rows, error=None) -> _Connection:
    return _Connection(_Cursor([(name,) for name in columns], rows, error))


def test_identifiers_are_quoted_exactly_and_escape_embedded_quotes():
    assert quote_identifier("ORDERS") == '"ORDERS"'
    assert quote_identifier('My "Q" Table') == '"My ""Q"" Table"'
    assert qualified_identifier("Sales DB", "PUBLIC", "T") == '"Sales DB"."PUBLIC"."T"'


def test_show_views_reads_lowercase_show_columns_and_flags():
    connection = _connection(
        ["created_on", "name", "text", "is_secure", "is_materialized"],
        [
            (None, "V_SALES", "create view V_SALES as select 1 as A", "false", "false"),
            (None, "MV_SALES", "create materialized view ...", "false", "true"),
            (None, "SECURE_V", "", "true", "false"),
        ],
    )

    views = SnowflakeMetadataClient().show_views(
        connection,
        database="Sales DB",
        schema_name="MART",
    )

    sql, parameters, timeout = connection.query_cursor.executed[0]
    assert sql.startswith('SHOW VIEWS IN SCHEMA "Sales DB"."MART"')
    assert "LIMIT 10000" in sql
    # SHOW is sent verbatim: no parameters means no %-formatting at all.
    assert parameters is None
    assert timeout and timeout > 0
    assert [view.name for view in views] == ["V_SALES", "MV_SALES", "SECURE_V"]
    assert views[1].is_materialized is True
    # A hidden (secure) definition is reported as missing, not as "".
    assert views[2].text is None
    assert views[2].is_secure is True
    assert connection.query_cursor.closed is True


def test_get_ddl_binds_the_type_and_the_quoted_name():
    connection = _connection(["DDL"], [("create or replace view X as select 1",)])

    ddl = SnowflakeMetadataClient().get_ddl(
        connection,
        object_type="VIEW",
        database="DB",
        schema_name="Mixed Case",
        object_name="V",
    )

    sql, parameters, _ = connection.query_cursor.executed[0]
    assert sql == "SELECT GET_DDL(%s, %s) AS DDL"
    assert parameters == ("VIEW", '"DB"."Mixed Case"."V"')
    assert ddl == "create or replace view X as select 1"


def test_table_columns_binds_the_name_list_as_one_parameter_and_formats_types():
    connection = _connection(
        [
            "TABLE_NAME",
            "COLUMN_NAME",
            "ORDINAL_POSITION",
            "DATA_TYPE",
            "CHARACTER_MAXIMUM_LENGTH",
            "NUMERIC_PRECISION",
            "NUMERIC_SCALE",
        ],
        [
            ("ORDERS", "ID", 1, "NUMBER", None, 38, 0),
            ("ORDERS", "NAME", 2, "TEXT", 16777216, None, None),
            ("ORDERS", "AT", 3, "TIMESTAMP_NTZ", None, None, None),
        ],
    )

    columns = SnowflakeMetadataClient().table_columns(
        connection,
        database="DB",
        schema_name="CORE",
        table_names=["ORDERS", "LINES"],
    )

    sql, parameters, _ = connection.query_cursor.executed[0]
    assert 'FROM "DB".INFORMATION_SCHEMA.COLUMNS' in sql
    assert "TABLE_NAME IN (%s)" in sql
    assert parameters == ("CORE", ["ORDERS", "LINES"])
    assert [(item.column_name, item.data_type) for item in columns] == [
        ("ID", "NUMBER(38,0)"),
        ("NAME", "VARCHAR(16777216)"),
        ("AT", "TIMESTAMP_NTZ"),
    ]


def test_table_columns_with_no_names_runs_nothing():
    connection = _connection(["TABLE_NAME"], [])

    assert (
        SnowflakeMetadataClient().table_columns(
            connection, database="DB", schema_name="S", table_names=[]
        )
        == []
    )
    assert connection.query_cursor.executed == []


_HISTORY_COLUMNS = [
    "QUERY_ID",
    "QUERY_TEXT",
    "QUERY_TYPE",
    "DATABASE_NAME",
    "SCHEMA_NAME",
    "START_TIME",
]


def test_recent_history_pages_with_coverage_and_binds_every_value():
    started = datetime(2026, 9, 1, 10, 0, tzinfo=timezone(timedelta(hours=-7)))
    oldest = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    connection = _connection(
        ["SCANNED", "OLDEST", *_HISTORY_COLUMNS],
        [
            (
                10000,
                oldest,
                "q1",
                "insert into ORDERS select 1",
                "INSERT",
                "DB",
                "CORE",
                started,
            )
        ],
    )

    page = SnowflakeMetadataClient().recent_history(
        connection,
        name_patterns=["%ORDERS%"],
        query_ids=["q9"],
        database="DB",
        end_before=None,
        limit=500,
    )

    sql, parameters, timeout = connection.query_cursor.executed[0]
    assert 'TABLE("DB".INFORMATION_SCHEMA.QUERY_HISTORY(' in sql
    assert "RESULT_LIMIT => 10000" in sql
    assert "QUERY_TEXT ILIKE ANY (%s) ESCAPE '!'" in sql
    assert "UPPER(EXECUTION_STATUS) = 'SUCCESS'" in sql
    assert "'CREATE_TABLE_AS_SELECT'" in sql and "'MERGE'" in sql
    # INSERT ... VALUES carries data, never logic.
    assert "NOT CONTAINS(UPPER(QUERY_TEXT), 'SELECT')" in sql
    # The window stays inside the function's 7 days, with a margin.
    assert parameters == (-10070, ["q9"], "%INSERT%", ["%ORDERS%"], ["q9"], 500)
    assert timeout >= 120
    # Every literal % lives in a bound value, never in the SQL text.
    assert sql.count("%") == sql.count("%s")
    assert page.scanned == 10000
    assert page.oldest_end_time == oldest
    assert page.records[0].query_id == "q1"
    assert page.records[0].start_time == datetime(2026, 9, 1, 17, 0, tzinfo=UTC)


def test_a_later_history_page_ends_where_the_previous_one_stopped():
    connection = _connection(["SCANNED", "OLDEST", *_HISTORY_COLUMNS], [])
    end_before = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

    SnowflakeMetadataClient().recent_history(
        connection,
        name_patterns=["%ORDERS%"],
        query_ids=[],
        database=None,
        end_before=end_before,
        limit=10,
    )

    sql, parameters, _ = connection.query_cursor.executed[0]
    assert "END_TIME_RANGE_END => TO_TIMESTAMP_LTZ(%s, 3)" in sql
    # With no database to qualify it, the session's own is used.
    assert "TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(" in sql
    assert parameters[1] == int(end_before.timestamp() * 1000)


def test_access_history_finds_each_tables_writers_by_resolved_target():
    connection = _connection(
        ["TARGET_NAME", *_HISTORY_COLUMNS],
        [("DB.CORE.ORDERS", "q1", "merge into x", "MERGE", "DB", "CORE", None)],
    )

    writes = SnowflakeMetadataClient().access_history_writes(
        connection,
        qualified_names=["DB.CORE.Orders"],
        lookback_days=90,
        per_table=5,
    )

    sql, parameters, timeout = connection.query_cursor.executed[0]
    assert "SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY" in sql
    assert "FLATTEN(INPUT => AH.OBJECTS_MODIFIED)" in sql
    assert "JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY" in sql
    assert parameters == (-90, ["DB.CORE.ORDERS"], -90, 5)
    assert timeout >= 300
    assert writes[0][0] == "DB.CORE.ORDERS"
    assert writes[0][1].query_type == "MERGE"


def test_account_usage_text_search_and_id_lookup_bound_the_scan_by_time():
    search = _connection(_HISTORY_COLUMNS, [])
    by_id = _connection(
        _HISTORY_COLUMNS,
        [("q1", "insert into T select 1", "INSERT", None, None, datetime(2026, 9, 1))],
    )
    client = SnowflakeMetadataClient()

    client.account_usage_writes(
        search, name_patterns=["%ORDERS%"], lookback_days=90, limit=500
    )
    records = client.account_usage_queries(
        by_id, query_ids=["q1", "q2"], lookback_days=365
    )

    sql, parameters, _ = search.query_cursor.executed[0]
    assert "FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY" in sql
    assert "START_TIME >= DATEADD('day', %s, CURRENT_TIMESTAMP())" in sql
    assert parameters == (-90, "%INSERT%", ["%ORDERS%"], 500)
    sql, parameters, _ = by_id.query_cursor.executed[0]
    assert "QUERY_ID IN (%s)" in sql and "START_TIME >=" in sql
    assert parameters == (-365, ["q1", "q2"])
    # Naive timestamps are taken as UTC.
    assert records[0].start_time == datetime(2026, 9, 1, tzinfo=UTC)


def test_like_patterns_escape_the_wildcards_table_names_contain():
    assert contains_pattern("DIM_DATE") == "%DIM!_DATE%"
    assert contains_pattern("100%!") == "%100!%!!%"


def test_show_objects_reports_dynamic_and_external_tables():
    connection = _connection(
        ["name", "kind", "is_dynamic"],
        [("V", "VIEW", "false"), ("DT", "TABLE", "true"), ("T", "TABLE", "false")],
    )

    objects = SnowflakeMetadataClient().show_objects(
        connection, database="DB", schema_name="S"
    )

    assert connection.query_cursor.executed[0][0].startswith(
        'SHOW OBJECTS IN SCHEMA "DB"."S"'
    )
    assert objects["V"].kind == "VIEW"
    assert objects["DT"].is_dynamic is True
    assert objects["T"].is_dynamic is False


def test_driver_errors_are_wrapped_with_the_reason():
    connection = _connection(
        ["DDL"],
        [],
        error=RuntimeError(
            "002003 (42S02): SQL compilation error: does not exist or not authorized"
        ),
    )

    with pytest.raises(UpstreamRequestError) as raised:
        SnowflakeMetadataClient().get_ddl(
            connection,
            object_type="VIEW",
            database="DB",
            schema_name="S",
            object_name="V",
        )

    assert "not authorized" in raised.value.message
    assert connection.query_cursor.closed is True
