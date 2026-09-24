from threading import Lock
from time import sleep

from app.clients.snowflake_lineage_query_client import (
    SnowflakeLineageQueryClient,
)
from app.core.exceptions import UpstreamRequestError
from app.schemas.snowflake_lineage import (
    SnowflakeDeepLineageRequest,
    SnowflakeLineageWarning,
)
from app.services.snowflake_deep_lineage_service import (
    SnowflakeDeepLineageService,
    _WarningCollector,
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


class _DriverError(Exception):
    """Stands in for a raw snowflake.connector error -- not an AppException."""


class _CursorFailingConnection:
    def __init__(self) -> None:
        self.calls = 0

    def cursor(self):
        self.calls += 1
        if self.calls == 1:
            return _Cursor()
        raise _DriverError("250002 (08003): Connection is closed")


def test_query_client_wraps_a_failure_to_open_a_cursor():
    # Opening the cursor used to sit outside the try block, so a driver error
    # there escaped every AppException handler and 500'd the whole request.
    connection = _CursorFailingConnection()
    connection.calls = 1

    try:
        SnowflakeLineageQueryClient().get_lineage(
            connection,
            object_name="DB.SCHEMA.TABLE",
            object_domain="TABLE",
            direction="UPSTREAM",
            max_distance=5,
        )
    except UpstreamRequestError as error:
        assert "Connection is closed" in error.message
    else:
        raise AssertionError("expected UpstreamRequestError")


class _DeepFailureQueryClient:
    """First batch succeeds; everything past level five fails."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def get_lineage(
        self,
        connection,
        *,
        object_name,
        object_domain,
        direction,
        max_distance,
    ):
        self.calls += 1
        if self.calls > 1:
            raise self.error
        return [
            _row(f"T{distance}", f"T{distance - 1}", distance=distance)
            for distance in range(1, 6)
        ]


def _trace_with(error: Exception):
    client = _DeepFailureQueryClient(error)
    return (
        SnowflakeDeepLineageService(query_client=client).trace(
            object(),
            account_identifier="acct",
            request=SnowflakeDeepLineageRequest(
                object_name="DB.SCHEMA.T0",
                column_name="VALUE",
                direction="UPSTREAM",
                max_depth=50,
            ),
        ),
        client,
    )


def test_a_failure_past_level_five_keeps_the_levels_already_walked():
    result, client = _trace_with(UpstreamRequestError("snowflake", detail="no access"))

    assert client.calls > 1
    assert result.truncated is True
    # The first five levels survive instead of the whole request failing.
    assert result.snapshot.object_count >= 6
    branch = next(
        warning
        for warning in result.warnings
        if warning.code == "SNOWFLAKE_LINEAGE_BRANCH_FAILED"
    )
    assert "no access" in branch.message


def test_a_raw_driver_error_past_level_five_does_not_fail_the_request():
    result, _ = _trace_with(_DriverError("250002 (08003): Connection is closed"))

    assert result.truncated is True
    assert result.snapshot.object_count >= 6
    branch = next(
        warning
        for warning in result.warnings
        if warning.code == "SNOWFLAKE_LINEAGE_BRANCH_FAILED"
    )
    assert "Connection is closed" in branch.message
    assert branch.root_object_name is not None


def test_a_root_query_failure_still_fails_the_request():
    # Nothing was traced at all, so a partial answer would be a lie.
    class _AlwaysFails:
        def get_lineage(self, connection, **kwargs):
            raise UpstreamRequestError("snowflake", detail="boom")

    try:
        SnowflakeDeepLineageService(query_client=_AlwaysFails()).trace(
            object(),
            account_identifier="acct",
            request=SnowflakeDeepLineageRequest(
                object_name="DB.SCHEMA.T0",
                column_name="VALUE",
            ),
        )
    except UpstreamRequestError:
        pass
    else:
        raise AssertionError("expected the root failure to propagate")


class _ChainQueryClient:
    """A linear chain; Snowflake only ever reveals five levels per call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def get_lineage(
        self,
        connection,
        *,
        object_name,
        object_domain,
        direction,
        max_distance,
    ):
        self.calls.append((object_name, max_distance))
        start = int(object_name.split(".")[2][1:])
        return [
            _row(f"T{start + distance}", f"T{start + distance - 1}", distance=distance)
            for distance in range(1, max_distance + 1)
        ]


def test_traversal_consolidates_past_snowflakes_five_level_cap():
    # GET_LINEAGE caps `distance` at 5, so depth 50 has to come from
    # re-rooting at each boundary and merging into one snapshot.
    client = _ChainQueryClient()

    result = SnowflakeDeepLineageService(query_client=client).trace(
        object(),
        account_identifier="acct",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.T0",
            column_name="VALUE",
            direction="UPSTREAM",
            max_depth=50,
        ),
    )

    assert all(max_distance <= 5 for _, max_distance in client.calls)
    assert len(client.calls) == 10  # 50 levels / 5 per query
    assert result.truncated is False
    assert max(edge.distance for edge in result.snapshot.dependencies) == 50
    assert result.snapshot.dependency_count == 50
    # One consolidated response, not ten stitched by the caller.
    assert result.max_depth == 50


def test_traversal_stops_at_max_depth_without_overshooting():
    client = _ChainQueryClient()

    result = SnowflakeDeepLineageService(query_client=client).trace(
        object(),
        account_identifier="acct",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.T0",
            column_name="VALUE",
            direction="UPSTREAM",
            max_depth=12,
        ),
    )

    assert max(edge.distance for edge in result.snapshot.dependencies) == 12
    # The last query asks for 2 levels, not 5, so Snowflake is not asked for
    # work that would be discarded.
    assert client.calls[-1][1] == 2


def test_warning_collector_deduplicates_and_caps():
    collector = _WarningCollector(max_warnings=3)

    for _ in range(100):
        collector.add(
            SnowflakeLineageWarning(
                code="SNOWFLAKE_LINEAGE_ROW_INVALID",
                message="same",
                root_object_name="DB.SCHEMA.T0",
            )
        )
    for index in range(100):
        collector.add(
            SnowflakeLineageWarning(
                code="SNOWFLAKE_LINEAGE_ROW_INVALID",
                message="same",
                root_object_name=f"DB.SCHEMA.T{index}",
            )
        )

    ordered = collector.ordered()

    assert collector.overflowed is True
    assert len(ordered) == 4  # 3 kept + the truncation notice
    assert ordered[-1].code == "SNOWFLAKE_LINEAGE_WARNINGS_TRUNCATED"


def test_warning_collector_is_silent_when_nothing_overflows():
    collector = _WarningCollector(max_warnings=10)
    collector.add(SnowflakeLineageWarning(code="A", message="a", root_object_name=None))
    collector.add(SnowflakeLineageWarning(code="A", message="a", root_object_name=None))

    assert collector.overflowed is False
    assert [warning.code for warning in collector.ordered()] == ["A"]


def _container_row(
    source,
    target,
    *,
    distance,
    source_domain,
    target_domain,
    column="VALUE",
):
    """A column-level row: Snowflake reports the *container's* domain."""
    row = _row(
        source,
        target,
        distance=distance,
        source_column=column,
        target_column=column,
    )
    row["SOURCE_OBJECT_DOMAIN"] = source_domain
    row["TARGET_OBJECT_DOMAIN"] = target_domain
    return row


class _DomainRecordingClient:
    def __init__(
        self,
        boundary_domain: str = "TABLE",
        column: str | None = "VALUE",
    ) -> None:
        self.boundary_domain = boundary_domain
        self.column = column
        self.calls: list[tuple[str, str]] = []

    def get_lineage(
        self,
        connection,
        *,
        object_name,
        object_domain,
        direction,
        max_distance,
    ):
        self.calls.append((object_name, object_domain))
        if len(self.calls) > 1:
            return []
        return [
            _container_row(
                f"T{distance}",
                f"T{distance - 1}",
                distance=distance,
                source_domain=(self.boundary_domain if distance == 5 else "TABLE"),
                target_domain="TABLE",
                column=self.column,
            )
            for distance in range(1, 6)
        ]


def test_a_column_boundary_is_requeried_as_a_column_not_as_its_container():
    # The boundary row says TABLE (the container), but `qualified_name`
    # carries the column. Sending TABLE with a four-part name made Snowflake
    # read the whole string as a table: "Table 'DB.S.T.COL' does not exist".
    client = _DomainRecordingClient()

    SnowflakeDeepLineageService(query_client=client).trace(
        object(),
        account_identifier="acct",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.T0",
            column_name="VALUE",
            direction="UPSTREAM",
            max_depth=50,
        ),
    )

    assert len(client.calls) == 2
    reroot_name, reroot_domain = client.calls[1]
    assert reroot_name == "DB.SCHEMA.T5.VALUE"
    assert reroot_domain == "COLUMN"


def test_a_view_boundary_is_traversed_rather_than_silently_dropped():
    client = _DomainRecordingClient(boundary_domain="VIEW")

    result = SnowflakeDeepLineageService(query_client=client).trace(
        object(),
        account_identifier="acct",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.T0",
            column_name="VALUE",
            direction="UPSTREAM",
            max_depth=50,
        ),
    )

    assert client.calls[1] == ("DB.SCHEMA.T5.VALUE", "COLUMN")
    assert not [
        warning
        for warning in result.warnings
        if warning.code == "SNOWFLAKE_LINEAGE_BOUNDARY_SKIPPED"
    ]


def test_an_untraversable_boundary_is_reported_instead_of_dropped():
    # Object-level lineage: with no column, the container's domain is what
    # decides whether the walk can continue.
    client = _DomainRecordingClient(boundary_domain="STAGE", column=None)

    result = SnowflakeDeepLineageService(query_client=client).trace(
        object(),
        account_identifier="acct",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.T0",
            direction="UPSTREAM",
            max_depth=50,
        ),
    )

    skipped = [
        warning
        for warning in result.warnings
        if warning.code == "SNOWFLAKE_LINEAGE_BOUNDARY_SKIPPED"
    ]
    assert skipped and "STAGE" in skipped[0].message


class _RootEchoClient:
    def get_lineage(
        self,
        connection,
        *,
        object_name,
        object_domain,
        direction,
        max_distance,
    ):
        # Snowflake reports the root itself as the TABLE that holds the column.
        return [
            _container_row(
                "T1",
                "T0",
                distance=1,
                source_domain="TABLE",
                target_domain="TABLE",
            )
        ]


def test_the_requested_root_column_is_not_duplicated_by_its_container():
    result = SnowflakeDeepLineageService(query_client=_RootEchoClient()).trace(
        object(),
        account_identifier="acct",
        request=SnowflakeDeepLineageRequest(
            object_name="DB.SCHEMA.T0",
            column_name="VALUE",
            direction="UPSTREAM",
            max_depth=5,
        ),
    )

    roots = [
        item
        for item in result.snapshot.objects
        if item.qualified_name == "DB.SCHEMA.T0.VALUE"
    ]
    assert len(roots) == 1
    # And it carries Snowflake's real container domain, not the request's.
    assert roots[0].object_domain == "TABLE"
    # The root is connected, rather than sitting beside the graph edgeless.
    assert result.snapshot.dependencies[0].target.object_id == roots[0].object_id
