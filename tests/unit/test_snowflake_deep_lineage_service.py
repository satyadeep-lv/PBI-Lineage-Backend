from threading import Lock
from time import sleep

from app.clients.snowflake_lineage_query_client import (
    SnowflakeLineageQueryClient,
)
from app.core.exceptions import UpstreamRequestError
from app.schemas.snowflake_lineage import SnowflakeDeepLineageRequest
from app.services.snowflake_deep_lineage_service import (
    SnowflakeDeepLineageService,
)


def _row(
    source: str,
    target: str,
    *,
    distance: int,
    domain: str = "COLUMN",
    source_column: str | None = "VALUE",
    target_column: str | None = "VALUE",
) -> dict:
    return {
        "DISTANCE": distance,
        "SOURCE_OBJECT_DATABASE": "DB",
        "SOURCE_OBJECT_SCHEMA": "SCHEMA",
        "SOURCE_OBJECT_NAME": source,
        "SOURCE_OBJECT_DOMAIN": domain,
        "SOURCE_COLUMN_NAME": source_column,
        "SOURCE_STATUS": "ACTIVE",
        "TARGET_OBJECT_DATABASE": "DB",
        "TARGET_OBJECT_SCHEMA": "SCHEMA",
        "TARGET_OBJECT_NAME": target,
        "TARGET_OBJECT_DOMAIN": domain,
        "TARGET_COLUMN_NAME": target_column,
        "TARGET_STATUS": "ACTIVE",
        "PROCESS": {"type": "QUERY"},
    }


class _ParallelQueryClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    def get_lineage(
        self,
        connection,
        *,
        object_name,
        object_domain,
        direction,
        max_distance,
    ):
        with self.lock:
            self.calls.append((object_name, max_distance))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if object_name == "DB.SCHEMA.TARGET.VALUE":
                return [
                    _row(f"SOURCE_{index}", "TARGET", distance=5) for index in range(7)
                ]
            sleep(0.02)
            source_name = object_name.split(".")[-2]
            index = source_name.rsplit("_", 1)[-1]
            return [_row(f"DEEP_{index}", source_name, distance=1)]
        finally:
            with self.lock:
                self.active -= 1


def test_deep_column_lineage_expands_seven_frontier_nodes_in_parallel():
    query_client = _ParallelQueryClient()
    service = SnowflakeDeepLineageService(query_client=query_client)

    result = service.trace(
        object(),
        account_identifier="organization-account",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.TARGET",
            column_name="VALUE",
            max_depth=6,
            max_concurrency=7,
        ),
    )

    assert result.object_domain == "COLUMN"
    assert result.query_count == 8
    assert result.snapshot.object_count == 15
    assert result.snapshot.dependency_count == 14
    assert max(edge.distance or 0 for edge in result.snapshot.dependencies) == 6
    assert query_client.max_active >= 2
    assert result.truncated is False


class _StaticQueryClient:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str, int]] = []

    def get_lineage(
        self,
        connection,
        *,
        object_name,
        object_domain,
        direction,
        max_distance,
    ):
        self.calls.append((object_name, object_domain, max_distance))
        return self.rows


def test_table_lineage_uses_table_domain_without_column_suffix():
    query_client = _StaticQueryClient(
        [
            _row(
                "SOURCE_TABLE",
                "TARGET_TABLE",
                distance=1,
                domain="TABLE",
                source_column=None,
                target_column=None,
            )
        ]
    )

    result = SnowflakeDeepLineageService(query_client=query_client).trace(
        object(),
        account_identifier="organization-account",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.TARGET_TABLE",
            max_depth=1,
        ),
    )

    assert result.object_domain == "TABLE"
    assert query_client.calls == [("DB.SCHEMA.TARGET_TABLE", "TABLE", 1)]
    assert result.snapshot.dependency_count == 1


def test_already_visited_five_level_frontier_is_not_queried_again():
    query_client = _StaticQueryClient([_row("TARGET", "TARGET", distance=5)])

    result = SnowflakeDeepLineageService(query_client=query_client).trace(
        object(),
        account_identifier="organization-account",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.TARGET",
            column_name="VALUE",
            max_depth=10,
        ),
    )

    assert result.query_count == 1
    assert any(
        warning.code == "SNOWFLAKE_LINEAGE_CYCLE_SKIPPED" for warning in result.warnings
    )


def test_query_limit_marks_response_truncated():
    query_client = _StaticQueryClient([_row("SOURCE", "TARGET", distance=5)])

    result = SnowflakeDeepLineageService(query_client=query_client).trace(
        object(),
        account_identifier="organization-account",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.TARGET",
            column_name="VALUE",
            max_depth=10,
            max_queries=1,
        ),
    )

    assert result.truncated is True
    assert result.query_count == 1
    assert any(
        warning.code == "SNOWFLAKE_LINEAGE_QUERY_LIMIT_REACHED"
        for warning in result.warnings
    )


class _QuotedBoundaryQueryClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_lineage(self, connection, *, object_name, **kwargs):
        self.calls.append(object_name)
        if len(self.calls) > 1:
            return []
        row = _row("Order.Items", "TARGET", distance=5)
        row.update(
            SOURCE_OBJECT_DATABASE="Sales DB",
            SOURCE_OBJECT_SCHEMA="Public Data",
            SOURCE_COLUMN_NAME="Unit Price",
        )
        return [row]


def test_five_level_boundary_requotes_case_sensitive_identifiers():
    query_client = _QuotedBoundaryQueryClient()

    SnowflakeDeepLineageService(query_client=query_client).trace(
        object(),
        account_identifier="organization-account",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.TARGET",
            column_name="VALUE",
            max_depth=6,
        ),
    )

    assert query_client.calls == [
        "DB.SCHEMA.TARGET.VALUE",
        '"Sales DB"."Public Data"."Order.Items"."Unit Price"',
    ]


class _FailingBranchQueryClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_lineage(self, connection, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return [_row("SOURCE", "TARGET", distance=5)]
        raise UpstreamRequestError("snowflake")


def test_non_root_branch_failure_returns_partial_lineage_with_warning():
    result = SnowflakeDeepLineageService(
        query_client=_FailingBranchQueryClient()
    ).trace(
        object(),
        account_identifier="organization-account",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.TARGET",
            column_name="VALUE",
            max_depth=10,
        ),
    )

    assert result.snapshot.dependency_count == 1
    assert result.truncated is True
    assert any(
        warning.code == "SNOWFLAKE_LINEAGE_BRANCH_FAILED" for warning in result.warnings
    )


class _DownstreamQueryClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_lineage(self, connection, *, object_name, **kwargs):
        self.calls.append(object_name)
        if len(self.calls) == 1:
            return [_row("ROOT", "CHILD", distance=5)]
        return []


def test_downstream_traversal_continues_from_target_boundary():
    query_client = _DownstreamQueryClient()

    result = SnowflakeDeepLineageService(query_client=query_client).trace(
        object(),
        account_identifier="organization-account",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.ROOT",
            column_name="VALUE",
            direction="DOWNSTREAM",
            max_depth=6,
        ),
    )

    assert result.direction == "DOWNSTREAM"
    assert query_client.calls == [
        "DB.SCHEMA.ROOT.VALUE",
        "DB.SCHEMA.CHILD.VALUE",
    ]


def test_process_evidence_can_be_omitted():
    result = SnowflakeDeepLineageService(
        query_client=_StaticQueryClient([_row("SOURCE", "TARGET", distance=1)])
    ).trace(
        object(),
        account_identifier="organization-account",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.TARGET",
            column_name="VALUE",
            max_depth=1,
            include_process=False,
        ),
    )

    assert result.snapshot.dependencies[0].process is None


class _Cursor:
    def __init__(self) -> None:
        self.description = [("DISTANCE",), ("PROCESS",)]
        self.parameters = None
        self.closed = False

    def execute(self, query, parameters):
        self.parameters = parameters

    def fetchall(self):
        return [(1, '{"type":"QUERY"}')]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self) -> None:
        self.query_cursor = _Cursor()

    def cursor(self):
        return self.query_cursor


def test_query_client_binds_get_lineage_arguments_and_decodes_process():
    connection = _Connection()

    rows = SnowflakeLineageQueryClient().get_lineage(
        connection,
        object_name="DB.SCHEMA.TABLE.COLUMN",
        object_domain="COLUMN",
        direction="UPSTREAM",
        max_distance=5,
    )

    assert connection.query_cursor.parameters == (
        "DB.SCHEMA.TABLE.COLUMN",
        "COLUMN",
        "UPSTREAM",
        5,
    )
    assert rows[0]["PROCESS"] == {"type": "QUERY"}
    assert connection.query_cursor.closed is True
