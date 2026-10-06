from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import UpstreamInvalidResponseError, UpstreamRequestError
from app.services.auth.snowflake_session_store import SnowflakeConnection

# Every statement here is a read. Identifiers cannot be bound, so they are
# double-quoted exactly as Snowflake stores them; every value is bound.
# pyformat binding renders a list as a comma-separated list of quoted values,
# so "IN (%s)" takes one list parameter, and no SQL text below may contain a
# bare % (it would be read as a placeholder).

# The connection's 60 s network_timeout is otherwise a client-side cancel on
# every statement. History scans can legitimately take longer.
_METADATA_TIMEOUT_SECONDS = 60
_HISTORY_TIMEOUT_SECONDS = 180
_ACCOUNT_USAGE_TIMEOUT_SECONDS = 300
# SHOW errors out above 10,000 rows unless LIMIT is given.
_SHOW_LIMIT = 10000
# INFORMATION_SCHEMA.QUERY_HISTORY applies its time range and RESULT_LIMIT
# before any WHERE clause: one call only ever sees the 10,000 most recent
# visible statements. The window must also stay inside the last 7 days or the
# call errors, hence the few minutes of margin.
HISTORY_FUNCTION_RESULT_LIMIT = 10000
_RECENT_HISTORY_MINUTES = 7 * 24 * 60 - 10
# LIKE treats _ as a wildcard, and most table names contain one.
_LIKE_ESCAPE = "!"

# Statements that can write rows into a table. INSERT ALL / FIRST and INSERT
# OVERWRITE have no documented QUERY_TYPE of their own, hence the extra
# ILIKE '%INSERT%' at each call site. CREATE_TABLE covers CLONE.
WRITE_QUERY_TYPES = (
    "INSERT",
    "MERGE",
    "UPDATE",
    "COPY",
    "CREATE_TABLE_AS_SELECT",
    "CREATE_TABLE",
)
_HISTORY_COLUMNS = (
    "QUERY_ID, QUERY_TEXT, QUERY_TYPE, DATABASE_NAME, SCHEMA_NAME, START_TIME"
)
# An INSERT with no SELECT anywhere is INSERT ... VALUES: it holds data, not
# transformation logic, and a row-by-row loader would otherwise crowd the
# real load statements out of every limit.
_NOT_VALUES_INSERT = (
    "NOT (QUERY_TYPE = 'INSERT' AND NOT CONTAINS(UPPER(QUERY_TEXT), 'SELECT'))"
)


@dataclass(frozen=True)
class SnowflakeSchemaObject:
    name: str
    kind: str
    is_dynamic: bool = False
    is_external: bool = False


@dataclass(frozen=True)
class SnowflakeViewDefinition:
    name: str
    text: str | None
    is_secure: bool = False
    is_materialized: bool = False


@dataclass(frozen=True)
class SnowflakeColumnInfo:
    table_name: str
    column_name: str
    ordinal_position: int
    data_type: str


@dataclass(frozen=True)
class SnowflakeQueryRecord:
    query_id: str
    query_text: str
    query_type: str | None
    database_name: str | None
    schema_name: str | None
    start_time: datetime | None


@dataclass(frozen=True)
class SnowflakeHistoryPage:
    """One INFORMATION_SCHEMA.QUERY_HISTORY call's matches and coverage."""

    records: list[SnowflakeQueryRecord] = field(default_factory=list)
    # Statements the function returned before filtering. At the limit, the
    # window was saturated and older statements were never looked at.
    scanned: int = 0
    oldest_end_time: datetime | None = None


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def qualified_identifier(*parts: str) -> str:
    return ".".join(quote_identifier(part) for part in parts)


def contains_pattern(name: str) -> str:
    """An ILIKE pattern matching `name` anywhere, wildcards escaped."""
    escaped = (
        name.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


class SnowflakeMetadataClient:
    def show_objects(
        self,
        connection: SnowflakeConnection,
        *,
        database: str,
        schema_name: str,
    ) -> dict[str, SnowflakeSchemaObject]:
        # Needs no warehouse. GET_LINEAGE reports views and dynamic tables as
        # TABLE, so this is where an object's real kind comes from.
        rows = self._fetch(
            connection,
            f"SHOW OBJECTS IN SCHEMA {qualified_identifier(database, schema_name)} "
            f"LIMIT {_SHOW_LIMIT}",
            None,
            timeout=_METADATA_TIMEOUT_SECONDS,
        )
        objects: dict[str, SnowflakeSchemaObject] = {}
        for row in rows:
            if not row.get("name"):
                continue
            kind = str(row.get("kind") or "").upper()
            objects[str(row["name"])] = SnowflakeSchemaObject(
                name=str(row["name"]),
                kind=kind,
                is_dynamic=self._flag(row.get("is_dynamic")),
                is_external=self._flag(row.get("is_external")) or "EXTERNAL" in kind,
            )
        return objects

    def show_views(
        self,
        connection: SnowflakeConnection,
        *,
        database: str,
        schema_name: str,
    ) -> list[SnowflakeViewDefinition]:
        # One warehouse-free call returns the CREATE text of every view and
        # materialized view in the schema -- except a secure view's, which
        # only its owner role sees.
        rows = self._fetch(
            connection,
            f"SHOW VIEWS IN SCHEMA {qualified_identifier(database, schema_name)} "
            f"LIMIT {_SHOW_LIMIT}",
            None,
            timeout=_METADATA_TIMEOUT_SECONDS,
        )
        return [
            SnowflakeViewDefinition(
                name=str(row["name"]),
                text=self._text(row.get("text")),
                is_secure=self._flag(row.get("is_secure")),
                is_materialized=self._flag(row.get("is_materialized"))
                or "MATERIALIZED" in str(row.get("kind") or "").upper(),
            )
            for row in rows
            if row.get("name")
        ]

    def show_dynamic_tables(
        self,
        connection: SnowflakeConnection,
        *,
        database: str,
        schema_name: str,
    ) -> dict[str, str | None]:
        # The text column needs OWNERSHIP or MONITOR on the dynamic table.
        rows = self._fetch(
            connection,
            "SHOW DYNAMIC TABLES IN SCHEMA "
            f"{qualified_identifier(database, schema_name)} LIMIT {_SHOW_LIMIT}",
            None,
            timeout=_METADATA_TIMEOUT_SECONDS,
        )
        return {
            str(row["name"]): self._text(row.get("text"))
            for row in rows
            if row.get("name")
        }

    def get_ddl(
        self,
        connection: SnowflakeConnection,
        *,
        object_type: str,
        database: str,
        schema_name: str,
        object_name: str,
    ) -> str | None:
        # object_type is VIEW (views and materialized views), TABLE (tables
        # and external tables) or DYNAMIC_TABLE.
        rows = self._fetch(
            connection,
            "SELECT GET_DDL(%s, %s) AS DDL",
            (object_type, qualified_identifier(database, schema_name, object_name)),
            timeout=_METADATA_TIMEOUT_SECONDS,
        )
        return self._text(rows[0].get("DDL")) if rows else None

    def table_columns(
        self,
        connection: SnowflakeConnection,
        *,
        database: str,
        schema_name: str,
        table_names: Sequence[str],
    ) -> list[SnowflakeColumnInfo]:
        if not table_names:
            return []
        # Equality on schema and an exact name list keeps INFORMATION_SCHEMA
        # selective enough not to refuse with "returned too much data".
        rows = self._fetch(
            connection,
            "SELECT TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION, DATA_TYPE, "
            "CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE "
            f"FROM {quote_identifier(database)}.INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN (%s) "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION",
            (schema_name, list(table_names)),
            timeout=_HISTORY_TIMEOUT_SECONDS,
        )
        return [
            SnowflakeColumnInfo(
                table_name=str(row["TABLE_NAME"]),
                column_name=str(row["COLUMN_NAME"]),
                ordinal_position=int(row.get("ORDINAL_POSITION") or 0),
                data_type=self._data_type(row),
            )
            for row in rows
            if row.get("TABLE_NAME") and row.get("COLUMN_NAME")
        ]

    def recent_history(
        self,
        connection: SnowflakeConnection,
        *,
        name_patterns: Sequence[str],
        query_ids: Sequence[str],
        database: str | None,
        end_before: datetime | None,
        limit: int,
    ) -> SnowflakeHistoryPage:
        """One page of the last 7 days from INFORMATION_SCHEMA.QUERY_HISTORY.

        The newest 10,000 statements visible to the role that ended before
        `end_before`: the caller's own, plus those on warehouses its role can
        MONITOR or OPERATE. Matches are write statements whose text mentions a
        name (the caller parses each to decide what it really wrote) and the
        statements named by id. Coverage comes back so the caller can page
        further back when the window was saturated.
        """
        conditions: list[str] = []
        parameters: list[Any] = []
        if query_ids:
            conditions.append("QUERY_ID IN (%s)")
            parameters.append(list(query_ids))
        if name_patterns:
            conditions.append(self._write_condition())
            parameters.extend(self._write_parameters(name_patterns))
        if not conditions:
            return SnowflakeHistoryPage()

        function = (
            f"{quote_identifier(database)}.INFORMATION_SCHEMA.QUERY_HISTORY"
            if database
            else "INFORMATION_SCHEMA.QUERY_HISTORY"
        )
        end = "CURRENT_TIMESTAMP()"
        leading: list[Any] = [-_RECENT_HISTORY_MINUTES]
        if end_before is not None:
            end = "TO_TIMESTAMP_LTZ(%s, 3)"
            leading.append(int(end_before.timestamp() * 1000))
        keep_named = "QUERY_ID IN (%s) OR " if query_ids else ""
        trailing: list[Any] = [list(query_ids)] if query_ids else []
        sql = (
            f"WITH H AS (SELECT {_HISTORY_COLUMNS}, END_TIME, EXECUTION_STATUS "
            f"FROM TABLE({function}("
            "END_TIME_RANGE_START => DATEADD('minute', %s, CURRENT_TIMESTAMP()), "
            f"END_TIME_RANGE_END => {end}, "
            f"RESULT_LIMIT => {HISTORY_FUNCTION_RESULT_LIMIT}))), "
            "COVERAGE AS (SELECT COUNT(*) AS SCANNED, MIN(END_TIME) AS OLDEST "
            "FROM H), "
            f"MATCHES AS (SELECT {_HISTORY_COLUMNS} FROM H "
            "WHERE UPPER(EXECUTION_STATUS) = 'SUCCESS' "
            f"AND ({' OR '.join(conditions)}) "
            f"QUALIFY {keep_named}ROW_NUMBER() OVER (PARTITION BY "
            "HASH(QUERY_TEXT, DATABASE_NAME, SCHEMA_NAME) "
            "ORDER BY START_TIME DESC) = 1 "
            "ORDER BY START_TIME DESC LIMIT %s) "
            f"SELECT C.SCANNED, C.OLDEST, M.* FROM COVERAGE C "
            "LEFT JOIN MATCHES M ON TRUE"
        )
        rows = self._fetch(
            connection,
            sql,
            (*leading, *parameters, *trailing, limit),
            timeout=_HISTORY_TIMEOUT_SECONDS,
        )
        if not rows:
            return SnowflakeHistoryPage()
        return SnowflakeHistoryPage(
            records=self._records(rows),
            scanned=int(rows[0].get("SCANNED") or 0),
            oldest_end_time=self._utc(rows[0].get("OLDEST")),
        )

    def access_history_writes(
        self,
        connection: SnowflakeConnection,
        *,
        qualified_names: Sequence[str],
        lookback_days: int,
        per_table: int,
    ) -> list[tuple[str, SnowflakeQueryRecord]]:
        """The statements that really wrote each table, from ACCESS_HISTORY.

        OBJECTS_MODIFIED holds each write's resolved target, so -- unlike a
        text search -- this cannot pick up a table that was only read, or a
        same-named table elsewhere, and it sees statements run inside
        procedures and tasks. Needs Enterprise Edition (as GET_LINEAGE does)
        and the GOVERNANCE_VIEWER database role or IMPORTED PRIVILEGES on
        SNOWFLAKE; lags by up to 3 hours.
        """
        if not qualified_names:
            return []
        target = "UPPER(REPLACE(OM.VALUE:\"objectName\"::STRING, '\"', ''))"
        sql = (
            f"WITH WRITES AS (SELECT DISTINCT AH.QUERY_ID, {target} AS TARGET_NAME "
            "FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY AH, "
            "LATERAL FLATTEN(INPUT => AH.OBJECTS_MODIFIED) OM "
            "WHERE AH.QUERY_START_TIME >= DATEADD('day', %s, CURRENT_TIMESTAMP()) "
            f"AND {target} IN (%s)), "
            "TEXTS AS (SELECT W.TARGET_NAME, Q.QUERY_ID, Q.QUERY_TEXT, Q.QUERY_TYPE, "
            "Q.DATABASE_NAME, Q.SCHEMA_NAME, Q.START_TIME "
            "FROM WRITES W JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY Q "
            "ON Q.QUERY_ID = W.QUERY_ID "
            "WHERE Q.START_TIME >= DATEADD('day', %s, CURRENT_TIMESTAMP()) "
            "AND Q.QUERY_TYPE NOT IN ('DELETE', 'TRUNCATE_TABLE', 'UNLOAD') "
            f"AND {_NOT_VALUES_INSERT.replace('QUERY_', 'Q.QUERY_')} "
            "QUALIFY ROW_NUMBER() OVER (PARTITION BY W.TARGET_NAME, "
            "HASH(Q.QUERY_TEXT, Q.DATABASE_NAME, Q.SCHEMA_NAME) "
            "ORDER BY Q.START_TIME DESC) = 1) "
            "SELECT * FROM TEXTS QUALIFY ROW_NUMBER() OVER "
            "(PARTITION BY TARGET_NAME ORDER BY START_TIME DESC) <= %s "
            "ORDER BY START_TIME DESC"
        )
        rows = self._fetch(
            connection,
            sql,
            (
                -lookback_days,
                [name.upper() for name in qualified_names],
                -lookback_days,
                per_table,
            ),
            timeout=_ACCOUNT_USAGE_TIMEOUT_SECONDS,
        )
        return [
            (str(row["TARGET_NAME"]), record)
            for row, record in zip(
                rows, self._records(rows, keep_all=True), strict=True
            )
            if record is not None and row.get("TARGET_NAME")
        ]

    def account_usage_writes(
        self,
        connection: SnowflakeConnection,
        *,
        name_patterns: Sequence[str],
        lookback_days: int,
        limit: int,
    ) -> list[SnowflakeQueryRecord]:
        """Text search of ACCOUNT_USAGE.QUERY_HISTORY, for when ACCESS_HISTORY
        is unavailable: the legacy procedure's approach, batched."""
        if not name_patterns:
            return []
        sql = (
            f"SELECT {_HISTORY_COLUMNS} FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY "
            "WHERE START_TIME >= DATEADD('day', %s, CURRENT_TIMESTAMP()) "
            "AND UPPER(EXECUTION_STATUS) = 'SUCCESS' "
            f"AND {self._write_condition()} "
            "QUALIFY ROW_NUMBER() OVER (PARTITION BY "
            "HASH(QUERY_TEXT, DATABASE_NAME, SCHEMA_NAME) "
            "ORDER BY START_TIME DESC) = 1 "
            "ORDER BY START_TIME DESC LIMIT %s"
        )
        rows = self._fetch(
            connection,
            sql,
            (-lookback_days, *self._write_parameters(name_patterns), limit),
            timeout=_ACCOUNT_USAGE_TIMEOUT_SECONDS,
        )
        return self._records(rows)

    def account_usage_queries(
        self,
        connection: SnowflakeConnection,
        *,
        query_ids: Sequence[str],
        lookback_days: int,
    ) -> list[SnowflakeQueryRecord]:
        """Specific statements by id. START_TIME bounds the scan: nothing says
        QUERY_ID alone prunes this view."""
        if not query_ids:
            return []
        rows = self._fetch(
            connection,
            f"SELECT {_HISTORY_COLUMNS} FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY "
            "WHERE START_TIME >= DATEADD('day', %s, CURRENT_TIMESTAMP()) "
            "AND QUERY_ID IN (%s)",
            (-lookback_days, list(query_ids)),
            timeout=_ACCOUNT_USAGE_TIMEOUT_SECONDS,
        )
        return self._records(rows)

    @staticmethod
    def _write_condition() -> str:
        types = ", ".join(f"'{query_type}'" for query_type in WRITE_QUERY_TYPES)
        return (
            f"((QUERY_TYPE IN ({types}) OR QUERY_TYPE ILIKE %s) "
            f"AND QUERY_TEXT ILIKE ANY (%s) ESCAPE '{_LIKE_ESCAPE}' "
            f"AND {_NOT_VALUES_INSERT})"
        )

    @staticmethod
    def _write_parameters(name_patterns: Sequence[str]) -> list[Any]:
        return ["%INSERT%", list(name_patterns)]

    def _records(
        self,
        rows: list[dict[str, Any]],
        *,
        keep_all: bool = False,
    ) -> list[Any]:
        records: list[Any] = []
        for row in rows:
            if not row.get("QUERY_ID") or not isinstance(row.get("QUERY_TEXT"), str):
                if keep_all:
                    records.append(None)
                continue
            records.append(
                SnowflakeQueryRecord(
                    query_id=str(row["QUERY_ID"]),
                    query_text=str(row["QUERY_TEXT"]),
                    query_type=self._text(row.get("QUERY_TYPE")),
                    database_name=self._text(row.get("DATABASE_NAME")),
                    schema_name=self._text(row.get("SCHEMA_NAME")),
                    start_time=self._utc(row.get("START_TIME")),
                )
            )
        return records

    def _fetch(
        self,
        connection: SnowflakeConnection,
        sql: str,
        parameters: Sequence[Any] | None,
        *,
        timeout: int,
    ) -> list[dict[str, Any]]:
        description = None
        rows: list[Any] = []
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(sql, parameters, timeout=timeout)
            description = cursor.description
            rows = cursor.fetchall()
        except Exception as exc:
            raise UpstreamRequestError("snowflake", detail=str(exc)) from exc
        finally:
            if cursor is not None:
                self._close(cursor)
        if not description:
            raise UpstreamInvalidResponseError("snowflake")
        # SHOW output columns are lower-case, query columns upper-case; keep
        # both spellings so callers can use whichever the statement returns.
        names = [str(item[0]) for item in description]
        mapped_rows: list[dict[str, Any]] = []
        for row in rows:
            if len(row) != len(names):
                raise UpstreamInvalidResponseError("snowflake")
            mapped = dict(zip(names, row, strict=True))
            for name, value in list(mapped.items()):
                mapped.setdefault(name.upper(), value)
                mapped.setdefault(name.lower(), value)
            mapped_rows.append(mapped)
        return mapped_rows

    @staticmethod
    def _data_type(row: dict[str, Any]) -> str:
        data_type = str(row.get("DATA_TYPE") or "").upper()
        length = row.get("CHARACTER_MAXIMUM_LENGTH")
        precision = row.get("NUMERIC_PRECISION")
        scale = row.get("NUMERIC_SCALE")
        if data_type == "TEXT":
            return f"VARCHAR({length})" if length else "VARCHAR"
        if data_type == "NUMBER" and precision is not None:
            return f"NUMBER({precision},{scale or 0})"
        return data_type

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text.strip() else None

    @staticmethod
    def _flag(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().casefold() in {"true", "y", "yes", "1"}

    @staticmethod
    def _utc(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _close(cursor: Any) -> None:
        try:
            cursor.close()
        except Exception:  # noqa: BLE001 - cursor cleanup boundary
            return
