from datetime import UTC, datetime
from threading import Lock
from time import sleep

import pytest

from app.clients.snowflake_metadata_client import (
    SnowflakeColumnInfo,
    SnowflakeHistoryPage,
    SnowflakeQueryRecord,
    SnowflakeSchemaObject,
    SnowflakeViewDefinition,
)
from app.core.exceptions import UpstreamRequestError
from app.schemas.snowflake_lineage import SnowflakeDeepLineageRequest
from app.services.snowflake_deep_lineage_service import SnowflakeDeepLineageService
from app.services.snowflake_transformation_service import (
    SnowflakeTransformationService,
    process_query_ids,
)

_QUERY_ID = "01b2c3d4-0000-1111-0000-000000000001"


def _row(
    source: str,
    target: str,
    *,
    source_column: str | None,
    target_column: str | None,
    distance: int = 1,
    source_schema: str = "CORE",
    target_schema: str = "MART",
    source_type: str | None = "TABLE",
    target_type: str | None = "TABLE",
    process=None,
) -> dict:
    return {
        "DISTANCE": distance,
        "SOURCE_OBJECT_DATABASE": "DB",
        "SOURCE_OBJECT_SCHEMA": source_schema,
        "SOURCE_OBJECT_NAME": source,
        "SOURCE_OBJECT_DOMAIN": "TABLE",
        "SOURCE_COLUMN_NAME": source_column,
        "SOURCE_STATUS": "ACTIVE",
        "TARGET_OBJECT_DATABASE": "DB",
        "TARGET_OBJECT_SCHEMA": target_schema,
        "TARGET_OBJECT_NAME": target,
        "TARGET_OBJECT_DOMAIN": "TABLE",
        "TARGET_COLUMN_NAME": target_column,
        "TARGET_STATUS": "ACTIVE",
        "PROCESS": process,
        "SOURCE_DETAILS": {"dataset_type": source_type} if source_type else None,
        "TARGET_DETAILS": {"dataset_type": target_type} if target_type else None,
    }


class _Lineage:
    """GET_LINEAGE answers keyed by the queried name; anything else is empty."""

    def __init__(self, answers: dict[str, list[dict]] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[str] = []

    def get_lineage(self, connection, *, object_name, **kwargs):
        self.calls.append(object_name)
        return self.answers.get(object_name, [])


def _record(
    query_id: str,
    text: str,
    *,
    query_type: str = "INSERT",
    database: str | None = "DB",
    schema_name: str | None = "CORE",
    day: int = 1,
) -> SnowflakeQueryRecord:
    return SnowflakeQueryRecord(
        query_id=query_id,
        query_text=text,
        query_type=query_type,
        database_name=database,
        schema_name=schema_name,
        start_time=datetime(2026, 9, day, tzinfo=UTC),
    )


class _Metadata:
    """Canned Snowflake metadata. SHOW OBJECTS lists every view, dynamic
    table and table with columns given here, so kinds come out right."""

    def __init__(
        self,
        *,
        views: dict[tuple[str, str], list[SnowflakeViewDefinition]] | None = None,
        dynamic_tables: dict[tuple[str, str], dict[str, str | None]] | None = None,
        ddl: dict[tuple[str, str, str], str] | None = None,
        columns: dict[tuple[str, str, str], list[tuple[str, str]]] | None = None,
        history: list[SnowflakeQueryRecord] | None = None,
        access: dict[str, list[SnowflakeQueryRecord]] | None = None,
        account_usage: list[SnowflakeQueryRecord] | None = None,
        by_id: dict[str, SnowflakeQueryRecord] | None = None,
        account_by_id: dict[str, SnowflakeQueryRecord] | None = None,
        failing: set[str] | None = None,
        delay: float = 0.0,
    ) -> None:
        self.views = views or {}
        self.dynamic_tables = dynamic_tables or {}
        self.ddl = ddl or {}
        self.columns = columns or {}
        self.history = history or []
        self.access = access or {}
        self.account_usage = account_usage or []
        self.by_id = by_id or {}
        self.account_by_id = account_by_id or {}
        self.failing = failing or set()
        self.delay = delay
        self.calls: list[tuple] = []
        self.lock = Lock()
        self.active = 0
        self.max_active = 0

    def _enter(self, *call) -> None:
        with self.lock:
            self.calls.append(call)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                sleep(self.delay)
            if call[0] in self.failing:
                raise UpstreamRequestError(
                    "snowflake",
                    detail="002003 (42S02): does not exist or not authorized",
                )
        finally:
            with self.lock:
                self.active -= 1

    def show_objects(self, connection, *, database, schema_name):
        self._enter("show_objects", database, schema_name)
        objects = {
            name: SnowflakeSchemaObject(name=name, kind="TABLE")
            for (db, schema, name) in self.columns
            if (db, schema) == (database, schema_name)
        }
        for name in self.dynamic_tables.get((database, schema_name), {}):
            objects[name] = SnowflakeSchemaObject(
                name=name, kind="TABLE", is_dynamic=True
            )
        for view in self.views.get((database, schema_name), []):
            objects[view.name] = SnowflakeSchemaObject(name=view.name, kind="VIEW")
        return objects

    def show_views(self, connection, *, database, schema_name):
        self._enter("show_views", database, schema_name)
        return self.views.get((database, schema_name), [])

    def show_dynamic_tables(self, connection, *, database, schema_name):
        self._enter("show_dynamic_tables", database, schema_name)
        return self.dynamic_tables.get((database, schema_name), {})

    def get_ddl(self, connection, *, object_type, database, schema_name, object_name):
        self._enter("get_ddl", object_type, database, schema_name, object_name)
        return self.ddl.get((database, schema_name, object_name))

    def table_columns(self, connection, *, database, schema_name, table_names):
        self._enter("table_columns", database, schema_name, tuple(table_names))
        return [
            SnowflakeColumnInfo(
                table_name=table,
                column_name=name,
                ordinal_position=position,
                data_type=data_type,
            )
            for table in table_names
            for position, (name, data_type) in enumerate(
                self.columns.get((database, schema_name, table), []), start=1
            )
        ]

    def recent_history(
        self, connection, *, name_patterns, query_ids, database, end_before, limit
    ):
        self._enter("recent_history", tuple(name_patterns), tuple(query_ids))
        records = list(self.history) if name_patterns else []
        records += [self.by_id[item] for item in query_ids if item in self.by_id]
        return SnowflakeHistoryPage(records=records, scanned=len(records))

    def access_history_writes(
        self, connection, *, qualified_names, lookback_days, per_table
    ):
        self._enter("access_history_writes", tuple(qualified_names))
        return [
            (name, record)
            for name in qualified_names
            for record in self.access.get(name, [])
        ]

    def account_usage_writes(self, connection, *, name_patterns, lookback_days, limit):
        self._enter("account_usage_writes", tuple(name_patterns))
        return self.account_usage

    def account_usage_queries(self, connection, *, query_ids, lookback_days):
        self._enter("account_usage_queries", tuple(query_ids))
        return [
            self.account_by_id[item] for item in query_ids if item in self.account_by_id
        ]

    def count(self, name: str) -> int:
        return sum(1 for call in self.calls if call[0] == name)


def _trace(
    lineage: _Lineage,
    metadata: _Metadata,
    **request,
):
    service = SnowflakeDeepLineageService(
        query_client=lineage,
        transformation_service=SnowflakeTransformationService(metadata_client=metadata),
    )
    return service.trace(
        object(),
        account_identifier="acct",
        request=SnowflakeDeepLineageRequest(**request),
    )


def _by_name(result) -> dict:
    return {item.qualified_name: item for item in result.transformations}


def test_view_and_table_columns_report_their_expressions_and_sql():
    view_sql = (
        "create or replace view DB.MART.V_SALES(NET_AMOUNT) as\n"
        "select o.amount * 0.9 from DB.CORE.ORDERS o"
    )
    lineage = _Lineage(
        {
            "DB.MART.V_SALES.NET_AMOUNT": [
                _row(
                    "ORDERS",
                    "V_SALES",
                    source_column="AMOUNT",
                    target_column="NET_AMOUNT",
                    target_type="VIEW",
                )
            ]
        }
    )
    metadata = _Metadata(
        views={("DB", "MART"): [SnowflakeViewDefinition("V_SALES", view_sql)]},
        history=[
            # The same table name in another database is not this table.
            _record(
                "decoy",
                "insert into OTHER.CORE.ORDERS (AMOUNT) select 1",
                database="OTHER",
                day=9,
            ),
            _record(
                "q1",
                "INSERT INTO ORDERS (ID, AMOUNT)\n"
                "SELECT r.id, r.amt::NUMBER(10,2) FROM RAW.ORDERS_RAW r",
            ),
        ],
        columns={
            ("DB", "CORE", "ORDERS"): [
                ("ID", "NUMBER(38,0)"),
                ("AMOUNT", "NUMBER(10,2)"),
            ]
        },
    )

    result = _trace(
        lineage,
        metadata,
        object_name="DB.MART.V_SALES",
        column_name="NET_AMOUNT",
    )
    rows = _by_name(result)

    root = rows["DB.MART.V_SALES.NET_AMOUNT"]
    assert root.lineage_level == 0
    assert root.parent_object_ids == []
    assert root.object_type == "VIEW"
    assert root.transformation_kind == "EXPRESSION"
    assert root.column_transformation == "o.amount * 0.9"
    assert root.modification_sql == view_sql
    assert root.modification_sql_source == "OBJECT_DDL"

    source = rows["DB.CORE.ORDERS.AMOUNT"]
    assert source.lineage_level == 1
    assert source.parent_qualified_names == ["DB.MART.V_SALES.NET_AMOUNT"]
    assert source.object_type == "TABLE"
    assert source.transformation_kind == "EXPRESSION"
    assert source.column_transformation == "r.amt::NUMBER(10,2)"
    assert source.modification_query_id == "q1"
    assert source.modification_query_type == "INSERT"
    assert source.modification_sql_source == "QUERY_HISTORY"
    assert source.modified_at == datetime(2026, 9, 1, tzinfo=UTC)

    # Found in the last 7 days, so the slow ACCOUNT_USAGE views are not touched.
    assert metadata.count("recent_history") == 1
    assert metadata.count("access_history_writes") == 0
    # The real object kinds reach the graph too, not just GET_LINEAGE's TABLE.
    types = {item.qualified_name: item.object_type for item in result.snapshot.objects}
    assert types["DB.MART.V_SALES.NET_AMOUNT"] == "VIEW"
    assert types["DB.CORE.ORDERS.AMOUNT"] == "TABLE"
    assert result.snapshot.dependencies[0].target.object_type == "VIEW"
    assert result.metadata_query_count > 0


_CTAS = _record(
    "old",
    "create or replace table DB.CORE.ORDERS as\n"
    "select id, amount_cents / 100 as amount from DB.RAW.R",
    query_type="CREATE_TABLE_AS_SELECT",
)


def test_access_history_is_searched_only_when_recent_history_has_nothing():
    metadata = _Metadata(
        access={"DB.CORE.ORDERS": [_CTAS]},
        columns={("DB", "CORE", "ORDERS"): [("AMOUNT", "NUMBER(10,2)")]},
    )

    result = _trace(
        _Lineage(),
        metadata,
        object_name="DB.CORE.ORDERS",
        column_name="AMOUNT",
        infer_missing_lineage=False,
    )

    root = result.transformations[0]
    assert root.object_type == "TABLE"
    assert root.column_transformation == "amount_cents / 100"
    assert root.modification_sql_source == "ACCESS_HISTORY"
    assert [call[0] for call in metadata.calls if "history" in call[0]] == [
        "recent_history",
        "access_history_writes",
    ]
    assert metadata.count("account_usage_writes") == 0


def test_without_access_history_the_query_text_is_searched_instead():
    metadata = _Metadata(
        account_usage=[_CTAS],
        columns={("DB", "CORE", "ORDERS"): [("AMOUNT", "NUMBER(10,2)")]},
        failing={"access_history_writes"},
    )

    result = _trace(
        _Lineage(),
        metadata,
        object_name="DB.CORE.ORDERS",
        column_name="AMOUNT",
        infer_missing_lineage=False,
    )

    root = result.transformations[0]
    assert root.column_transformation == "amount_cents / 100"
    assert root.modification_sql_source == "ACCOUNT_USAGE_QUERY_HISTORY"
    # The fallback worked, so the ACCESS_HISTORY refusal is not a warning.
    assert not [
        warning
        for warning in result.warnings
        if warning.code == "SNOWFLAKE_TRANSFORMATION_LOOKUP_FAILED"
    ]


def test_a_table_with_no_load_history_reports_its_column_type():
    metadata = _Metadata(
        columns={("DB", "CORE", "ORDERS"): [("AMOUNT", "NUMBER(10,2)")]},
    )

    result = _trace(
        _Lineage(),
        metadata,
        object_name="DB.CORE.ORDERS",
        column_name="AMOUNT",
        infer_missing_lineage=False,
        search_account_usage=False,
    )

    root = result.transformations[0]
    assert root.transformation_kind == "BASE_COLUMN"
    assert root.column_transformation == (
        "AMOUNT NUMBER(10,2) (base table column — no ingestion history found)"
    )
    assert root.modification_sql is None
    assert metadata.count("recent_history") == 1
    assert metadata.count("access_history_writes") == 0


def test_the_statement_get_lineage_names_wins_over_a_newer_one():
    lineage = _Lineage(
        {
            "DB.MART.SALES.TOTAL": [
                _row(
                    "ORDERS",
                    "SALES",
                    source_column="AMOUNT",
                    target_column="TOTAL",
                    process={"QUERY_ID": _QUERY_ID},
                )
            ]
        }
    )
    metadata = _Metadata(
        by_id={
            _QUERY_ID: _record(
                _QUERY_ID,
                "insert into MART.SALES (TOTAL) select sum(amount) from CORE.ORDERS",
                schema_name="MART",
            )
        },
        history=[
            _record(
                "newer",
                "insert into DB.MART.SALES (TOTAL) select 0",
                schema_name="MART",
                day=20,
            )
        ],
    )

    result = _trace(
        lineage,
        metadata,
        object_name="DB.MART.SALES",
        column_name="TOTAL",
        include_process=False,
    )

    root = _by_name(result)["DB.MART.SALES.TOTAL"]
    assert root.column_transformation == "sum(amount)"
    assert root.modification_sql_source == "LINEAGE_PROCESS"
    assert root.modification_query_id == _QUERY_ID
    # include_process=False hides PROCESS from the response, not from us.
    assert result.snapshot.dependencies[0].process is None


def test_missing_lineage_is_inferred_from_a_views_sql_and_verified():
    view_sql = (
        "create or replace view V_REV as select s.price * s.qty as revenue "
        "from CORE.SALES s join CORE.PRODUCTS p on p.id = s.product_id"
    )
    lineage = _Lineage()
    metadata = _Metadata(
        views={("DB", "MART"): [SnowflakeViewDefinition("V_REV", view_sql)]},
        columns={
            ("DB", "CORE", "SALES"): [
                ("PRICE", "NUMBER(10,2)"),
                ("QTY", "NUMBER(38,0)"),
                ("PRODUCT_ID", "NUMBER(38,0)"),
            ],
            ("DB", "CORE", "PRODUCTS"): [("ID", "NUMBER(38,0)")],
        },
    )

    result = _trace(
        lineage,
        metadata,
        object_name="DB.MART.V_REV",
        column_name="REVENUE",
        search_account_usage=False,
    )

    inferred = [
        edge
        for edge in result.snapshot.dependencies
        if edge.dependency_type == "SQL_INFERRED"
    ]
    assert sorted(edge.source.qualified_name for edge in inferred) == [
        "DB.CORE.SALES.PRICE",
        "DB.CORE.SALES.QTY",
    ]
    assert {edge.distance for edge in inferred} == {1}
    assert result.inferred_dependency_count == 2
    # The inferred columns are traced on through GET_LINEAGE in turn.
    assert "DB.CORE.SALES.PRICE" in lineage.calls
    assert any(
        warning.code == "SNOWFLAKE_LINEAGE_INFERRED"
        and warning.root_object_name == "DB.MART.V_REV.REVENUE"
        for warning in result.warnings
    )
    rows = _by_name(result)
    assert rows["DB.MART.V_REV.REVENUE"].column_transformation == "s.price * s.qty"
    assert rows["DB.CORE.SALES.PRICE"].lineage_level == 1
    assert rows["DB.CORE.SALES.PRICE"].transformation_kind == "BASE_COLUMN"


def test_an_unqualified_column_is_inferred_from_the_first_table_that_has_it():
    view_sql = "create view V as select amount from CORE.A join CORE.B on A.id = B.id"
    metadata = _Metadata(
        views={("DB", "MART"): [SnowflakeViewDefinition("V", view_sql)]},
        columns={
            ("DB", "CORE", "A"): [("ID", "NUMBER")],
            ("DB", "CORE", "B"): [("ID", "NUMBER"), ("AMOUNT", "NUMBER")],
        },
    )

    result = _trace(
        _Lineage(),
        metadata,
        object_name="DB.MART.V",
        column_name="AMOUNT",
        search_account_usage=False,
    )

    assert [
        edge.source.qualified_name
        for edge in result.snapshot.dependencies
        if edge.dependency_type == "SQL_INFERRED"
    ] == ["DB.CORE.B.AMOUNT"]


def test_a_reference_to_a_column_that_does_not_exist_is_not_inferred():
    view_sql = "create view V as select x.nope as amount from CORE.A x"
    metadata = _Metadata(
        views={("DB", "MART"): [SnowflakeViewDefinition("V", view_sql)]},
        columns={("DB", "CORE", "A"): [("ID", "NUMBER")]},
    )

    result = _trace(
        _Lineage(),
        metadata,
        object_name="DB.MART.V",
        column_name="AMOUNT",
        search_account_usage=False,
    )

    assert result.snapshot.dependencies == []
    assert result.inferred_dependency_count == 0


@pytest.mark.parametrize(
    "request_options",
    [
        {"direction": "DOWNSTREAM"},
        {"infer_missing_lineage": False},
    ],
)
def test_no_inference_downstream_or_when_disabled(request_options):
    view_sql = "create view V as select s.price as amount from CORE.SALES s"
    metadata = _Metadata(
        views={("DB", "MART"): [SnowflakeViewDefinition("V", view_sql)]},
        columns={("DB", "CORE", "SALES"): [("PRICE", "NUMBER")]},
    )

    result = _trace(
        _Lineage(),
        metadata,
        object_name="DB.MART.V",
        column_name="AMOUNT",
        **request_options,
    )

    assert result.snapshot.dependencies == []
    # The root's own transformation is still reported.
    assert result.transformations[0].column_transformation == (
        "s.price (passed through from source)"
    )


def test_nothing_is_read_when_transformations_and_inference_are_off():
    metadata = _Metadata()
    lineage = _Lineage(
        {"DB.MART.V.A": [_row("T", "V", source_column="A", target_column="A")]}
    )

    result = _trace(
        lineage,
        metadata,
        object_name="DB.MART.V",
        column_name="A",
        include_transformations=False,
        infer_missing_lineage=False,
    )

    assert metadata.calls == []
    assert result.transformations == []
    assert result.metadata_query_count == 0
    assert result.snapshot.dependency_count == 1


def test_failed_lookups_degrade_to_warnings_not_errors():
    metadata = _Metadata(
        failing={
            "show_objects",
            "show_views",
            "show_dynamic_tables",
            "recent_history",
            "access_history_writes",
            "account_usage_writes",
            "table_columns",
        }
    )

    result = _trace(
        _Lineage(),
        metadata,
        object_name="DB.CORE.ORDERS",
        column_name="AMOUNT",
    )

    root = result.transformations[0]
    assert root.transformation_kind == "NO_DEFINITION"
    assert root.column_transformation == (
        "AMOUNT (source — no transformation SQL found)"
    )
    failures = [
        warning
        for warning in result.warnings
        if warning.code == "SNOWFLAKE_TRANSFORMATION_LOOKUP_FAILED"
    ]
    assert failures
    assert all("not authorized" in warning.message for warning in failures)
    # Each failing lookup is attempted once, not once per caller.
    assert metadata.count("show_views") == 1


def test_each_schema_and_the_history_are_read_once_and_concurrently():
    rows = [
        _row(
            f"T{index}",
            "V",
            source_column="A",
            target_column="A",
            source_schema=f"S{index % 3}",
            target_type="VIEW",
        )
        for index in range(9)
    ]
    view_sql = "create view V as select 1 as a"
    metadata = _Metadata(
        views={("DB", "MART"): [SnowflakeViewDefinition("V", view_sql)]},
        delay=0.03,
    )

    result = _trace(
        _Lineage({"DB.MART.V.A": rows}),
        metadata,
        object_name="DB.MART.V",
        column_name="A",
        infer_missing_lineage=False,
        search_account_usage=False,
    )

    assert len(result.transformations) == 10
    # One history search covers all nine tables...
    assert metadata.count("recent_history") == 1
    # ...one column read per schema, not per table...
    assert metadata.count("table_columns") == 3
    # ...and the root's schema is listed once, though several paths ask.
    assert metadata.count("show_views") == 1
    assert metadata.max_active >= 2


def test_pass_through_and_direct_references_are_labelled():
    view_sql = (
        "create view V as select o.customer_id as client_id, customer_id "
        "from CORE.ORDERS o"
    )
    metadata = _Metadata(
        views={("DB", "MART"): [SnowflakeViewDefinition("V", view_sql)]},
    )

    renamed = _trace(
        _Lineage(),
        metadata,
        object_name="DB.MART.V",
        column_name="CLIENT_ID",
        infer_missing_lineage=False,
    ).transformations[0]
    direct = _trace(
        _Lineage(),
        metadata,
        object_name="DB.MART.V",
        column_name="CUSTOMER_ID",
        infer_missing_lineage=False,
    ).transformations[0]

    assert renamed.transformation_kind == "PASS_THROUGH"
    assert renamed.column_transformation == (
        "o.customer_id (passed through from source)"
    )
    assert direct.transformation_kind == "DIRECT_REFERENCE"
    assert direct.column_transformation == (
        "CUSTOMER_ID (direct column reference — no transformation)"
    )


def test_a_loading_statement_that_does_not_name_the_column_is_still_shown():
    metadata = _Metadata(
        history=[
            _record(
                "q1",
                "merge into DB.CORE.ORDERS t using DB.RAW.R s on t.id = s.id "
                "when matched then update set t.status = s.status",
                query_type="MERGE",
            )
        ],
    )

    root = _trace(
        _Lineage(),
        metadata,
        object_name="DB.CORE.ORDERS",
        column_name="AMOUNT",
        infer_missing_lineage=False,
        search_account_usage=False,
    ).transformations[0]

    assert root.transformation_kind == "INGESTION_QUERY"
    assert root.modification_query_id == "q1"
    assert "merge into DB.CORE.ORDERS" in root.modification_sql


def test_table_traces_report_each_objects_sql_without_a_column():
    view_sql = "create view V as select * from CORE.T"
    lineage = _Lineage(
        {
            "DB.MART.V": [
                _row(
                    "T",
                    "V",
                    source_column=None,
                    target_column=None,
                    target_type="VIEW",
                )
            ]
        }
    )
    metadata = _Metadata(
        views={("DB", "MART"): [SnowflakeViewDefinition("V", view_sql)]},
        history=[_record("q1", "insert into DB.CORE.T select * from DB.RAW.T")],
    )

    result = _trace(lineage, metadata, object_name="DB.MART.V")
    rows = _by_name(result)

    assert rows["DB.MART.V"].transformation_kind == "OBJECT"
    assert rows["DB.MART.V"].column_transformation is None
    assert rows["DB.MART.V"].modification_sql == view_sql
    assert rows["DB.CORE.T"].modification_query_id == "q1"


@pytest.mark.parametrize(
    ("process", "expected"),
    [
        ({"QUERY_ID": _QUERY_ID}, (_QUERY_ID,)),
        ({"queryId": _QUERY_ID}, (_QUERY_ID,)),
        ({"query_id": _QUERY_ID, "name": "x"}, (_QUERY_ID,)),
        ([{"process": {"queryId": _QUERY_ID}}], (_QUERY_ID,)),
        (_QUERY_ID, (_QUERY_ID,)),
        ({"procedure": "DB.S.LOAD"}, ()),
        ("not an id", ()),
        (None, ()),
    ],
)
def test_query_ids_are_found_in_any_process_shape(process, expected):
    assert process_query_ids(process) == expected
