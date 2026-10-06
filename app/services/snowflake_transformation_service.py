"""Column transformations and modification SQL for a Snowflake lineage trace.

GET_LINEAGE says which columns feed which; it does not say how. This module
reads the SQL behind every traced object -- a view's definition, or the
statements that loaded a table -- and reports each column's expression,
replacing the per-row heuristics of the legacy TRACE_COLUMN_LINEAGE procedure.

Everything is read once per trace and batched: one SHOW per schema and kind,
one INFORMATION_SCHEMA.COLUMNS query per schema, and one history search
covering every table and every statement GET_LINEAGE named, instead of the
procedure's several queries per lineage row. Lookups run concurrently, and a
lookup another thread already started is waited for rather than repeated.
"""

import re
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence, Set
from concurrent.futures import Executor, Future, wait
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from app.clients.snowflake_metadata_client import (
    HISTORY_FUNCTION_RESULT_LIMIT,
    SnowflakeColumnInfo,
    SnowflakeMetadataClient,
    SnowflakeQueryRecord,
    SnowflakeSchemaObject,
    SnowflakeViewDefinition,
    contains_pattern,
)
from app.domain.snowflake_sql import (
    SqlColumnSource,
    SqlColumnTransformation,
    SqlObjectName,
    collapse_whitespace,
    describe_statement,
    extract_column_transformation,
    referenced_tables,
    split_identifier,
)
from app.schemas.snowflake_lineage import (
    SnowflakeColumnTransformation,
    SnowflakeDeepLineageRequest,
    SnowflakeDependency,
    SnowflakeLineageWarning,
    SnowflakeObjectReference,
)
from app.services.auth.snowflake_session_store import SnowflakeConnection

ObjectKey = tuple[str, str, str]

# QUERY_TEXT is cut at 100K characters by ACCOUNT_USAGE; DDL can be longer.
_MAX_SQL_CHARS = 200_000
_HISTORY_TEXT_LIMIT = 100_000
_MAX_WARNING_DETAIL = 300
# Distinct write statements fetched per history call, and kept per table.
# Enough for every loader of every traced table without paging megabytes of
# SQL text; several per table so a column one loader does not set can still
# be found in another.
_HISTORY_LIMIT = 500
_STATEMENTS_PER_TABLE = 5
# Each INFORMATION_SCHEMA.QUERY_HISTORY call sees the 10,000 most recent
# statements; on a busy account that is minutes, not 7 days. Page further
# back this many times before leaving the rest to ACCOUNT_USAGE.
_HISTORY_PAGES = 3
_QUERY_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_QUERY_ID_KEY = re.compile(r"^query[_\s-]?ids?$", re.IGNORECASE)
_WRITE_STATEMENTS = frozenset(
    {
        "CREATE_TABLE_AS_SELECT",
        "CREATE_TABLE_CLONE",
        "INSERT",
        "MULTI_TABLE_INSERT",
        "MERGE",
        "UPDATE",
        "COPY",
    }
)
_DIRECT_REFERENCE_NOTE = "direct column reference — no transformation"


def object_key(reference: SnowflakeObjectReference) -> ObjectKey:
    return (reference.database, reference.schema_name, reference.object_name)


def process_query_ids(process: Any) -> tuple[str, ...]:
    """The query IDs a GET_LINEAGE PROCESS value names.

    PROCESS has no published schema -- only "it might include the query ID of
    a SQL query" -- so a key spelled like query_id, queryId or QUERY_ID (or
    its plural) is read at any depth. An id-shaped string is trusted on its
    own only as the whole value: OpenLineage edges carry UUID-shaped run ids,
    and parentQueryId / rootQueryId name a CALL, not the statement.
    """
    found: list[str] = []

    def accept(value: Any) -> None:
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and _QUERY_ID.match(item.strip()):
                found.append(item.strip())

    def visit(value: Any, depth: int) -> None:
        if depth > 6:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if _QUERY_ID_KEY.match(str(key)):
                    accept(item)
                else:
                    visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)

    if isinstance(process, str):
        accept(process)
    else:
        visit(process, 0)
    return tuple(dict.fromkeys(found))


def is_view_like(object_type: str | None) -> bool:
    return bool(object_type) and "VIEW" in object_type


def is_dynamic_table(object_type: str | None) -> bool:
    return bool(object_type) and "DYNAMIC" in object_type


def is_external_table(object_type: str | None) -> bool:
    return bool(object_type) and "EXTERNAL" in object_type


def is_loaded_table(object_type: str | None) -> bool:
    """A table whose rows come from statements rather than a definition."""
    return (
        bool(object_type)
        and "TABLE" in object_type
        and not is_dynamic_table(object_type)
        and not is_external_table(object_type)
    )


def _defined_by_ddl(object_type: str | None) -> bool:
    return (
        is_view_like(object_type)
        or is_dynamic_table(object_type)
        or is_external_table(object_type)
    )


@dataclass(frozen=True)
class InferredSource:
    """An upstream object or column read from SQL where GET_LINEAGE had none."""

    database: str
    schema_name: str
    object_name: str
    column_name: str | None = None
    object_type: str | None = None


@dataclass(frozen=True)
class TraceGraph:
    root_id: str
    direction: str
    nodes: Mapping[str, SnowflakeObjectReference]
    edges: Sequence[SnowflakeDependency]
    levels: Mapping[str, int]
    parents: Mapping[str, Set[str]]
    # Node id -> the statements GET_LINEAGE named as writing into it.
    process_query_ids: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class TransformationReport:
    transformations: list[SnowflakeColumnTransformation]
    object_types: dict[ObjectKey, str]


@dataclass(frozen=True)
class _Definition:
    """One piece of SQL that defines or loaded an object."""

    sql: str
    source: str
    database: str | None
    schema_name: str | None
    query_id: str | None = None
    query_type: str | None = None
    modified_at: datetime | None = None


class _Once:
    """Runs each key's computation once per trace, in the caller's thread.

    The future is registered only when a caller starts computing, never when
    work is queued, so a pool worker can only ever wait for a computation that
    is already running -- it cannot deadlock behind work queued after it.
    One computation may fill several keys (a batched query).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._futures: dict[Hashable, Future] = {}

    def get(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        return self.get_many([key], lambda missing: {key: compute()}).get(key)

    def get_many(
        self,
        keys: Iterable[Hashable],
        compute: Callable[[list[Hashable]], Mapping[Hashable, Any]],
    ) -> dict[Hashable, Any]:
        wanted = list(dict.fromkeys(keys))
        with self._lock:
            missing = [key for key in wanted if key not in self._futures]
            batch: Future | None = Future() if missing else None
            for key in missing:
                self._futures[key] = batch
            futures = {key: self._futures[key] for key in wanted}
        if batch is not None:
            try:
                batch.set_result(dict(compute(missing)))
            except BaseException as error:
                # Every waiter must be released, whatever happened.
                batch.set_exception(error)
                if not isinstance(error, Exception):
                    raise
        results: dict[Hashable, Any] = {}
        for key, future in futures.items():
            try:
                values = future.result()
            except Exception:  # noqa: BLE001 - the computing caller warned
                continue
            results[key] = values.get(key)
        return results


class SnowflakeTransformationService:
    def __init__(
        self,
        *,
        metadata_client: SnowflakeMetadataClient | None = None,
    ) -> None:
        self.metadata_client = metadata_client or SnowflakeMetadataClient()

    def open(
        self,
        connection: SnowflakeConnection,
        *,
        request: SnowflakeDeepLineageRequest,
        executor: Executor,
        warn: Callable[[SnowflakeLineageWarning], None],
    ) -> "TransformationSession":
        return TransformationSession(
            connection,
            client=self.metadata_client,
            request=request,
            executor=executor,
            warn=warn,
        )


class TransformationSession:
    """Definition reads for one trace; safe to call from several threads."""

    def __init__(
        self,
        connection: SnowflakeConnection,
        *,
        client: SnowflakeMetadataClient,
        request: SnowflakeDeepLineageRequest,
        executor: Executor,
        warn: Callable[[SnowflakeLineageWarning], None],
    ) -> None:
        self._connection = connection
        self._client = client
        self._request = request
        self._executor = executor
        self._warn = warn
        self._objects = _Once()
        self._views = _Once()
        self._dynamic_tables = _Once()
        self._ddl = _Once()
        self._columns = _Once()
        self._history = _Once()
        self._count_lock = Lock()
        self._query_count = 0
        self._history_database: str | None = None

    @property
    def query_count(self) -> int:
        with self._count_lock:
            return self._query_count

    # -- called from the traversal thread ---------------------------------

    def observe(self, references: Iterable[SnowflakeObjectReference]) -> None:
        """Start reading the schemas new nodes live in while the walk goes on."""
        schemas: set[tuple[str, str]] = set()
        views: set[tuple[str, str]] = set()
        dynamic_tables: set[tuple[str, str]] = set()
        for reference in references:
            database, schema_name, _ = object_key(reference)
            if not database or not schema_name:
                continue
            if self._history_database is None:
                self._history_database = database
            schema = (database, schema_name)
            schemas.add(schema)
            if reference.object_type is None or is_view_like(reference.object_type):
                views.add(schema)
            if is_dynamic_table(reference.object_type):
                dynamic_tables.add(schema)
        for database, schema_name in sorted(schemas):
            self._executor.submit(self._schema_objects, database, schema_name)
        for database, schema_name in sorted(views):
            self._executor.submit(self._schema_views, database, schema_name)
        for database, schema_name in sorted(dynamic_tables):
            self._executor.submit(self._schema_dynamic_tables, database, schema_name)

    def build(self, graph: TraceGraph) -> TransformationReport:
        """Every node's transformation. Runs on the traversal thread, after it."""
        nodes_by_object: dict[ObjectKey, list[SnowflakeObjectReference]] = defaultdict(
            list
        )
        for node in graph.nodes.values():
            nodes_by_object[object_key(node)].append(node)
        keys = [key for key in nodes_by_object if all(key)]
        hints = {
            key: next(
                (node.object_type for node in nodes if node.object_type),
                None,
            )
            for key, nodes in nodes_by_object.items()
        }
        object_types: dict[Any, Any] = self._gather(
            {key: (lambda key=key: self._object_type(key, hints[key])) for key in keys}
        )
        # An object whose kind could not be read is searched for as a table:
        # a view is never the target of a write, so the search can only find
        # statements that really loaded it.
        tables = [
            key
            for key in keys
            if object_types.get(key) is None or is_loaded_table(object_types[key])
        ]
        table_set = set(tables)
        query_ids: dict[ObjectKey, list[str]] = defaultdict(list)
        for key, nodes in nodes_by_object.items():
            for node in nodes:
                query_ids[key].extend(graph.process_query_ids.get(node.object_id, ()))
        tables_by_schema: dict[tuple[str, str], list[ObjectKey]] = defaultdict(list)
        for key in tables:
            tables_by_schema[(key[0], key[1])].append(key)

        # Everything left is independent: read it all at once.
        self._gather(
            {
                "history": lambda: self._history_for(
                    tables,
                    [query_id for key in tables for query_id in query_ids[key]],
                ),
                **{
                    ("columns", schema): (
                        lambda schema_keys=schema_keys: self._table_columns(schema_keys)
                    )
                    for schema, schema_keys in tables_by_schema.items()
                },
                **{
                    ("ddl", key): (
                        lambda key=key: self._object_ddl(key, object_types[key])
                    )
                    for key in keys
                    if _defined_by_ddl(object_types.get(key))
                },
            }
        )

        transformations: list[SnowflakeColumnTransformation] = []
        for key, nodes in nodes_by_object.items():
            object_type = object_types.get(key) or hints.get(key)
            definitions = (
                self._definitions(key, object_type, tuple(query_ids[key]))
                if all(key)
                else []
            )
            columns = self._table_columns([key]).get(key) if key in table_set else None
            for node in nodes:
                transformations.append(
                    self._transformation(
                        node,
                        object_type=object_type,
                        definitions=self._for_node(
                            definitions,
                            graph.process_query_ids.get(node.object_id),
                        ),
                        columns=columns,
                        graph=graph,
                    )
                )
        transformations.sort(
            key=lambda item: (item.lineage_level, item.qualified_name, item.object_id)
        )
        return TransformationReport(
            transformations=transformations,
            object_types={key: value for key, value in object_types.items() if value},
        )

    # -- called from metadata workers ---------------------------------------

    def infer_upstream(
        self,
        reference: SnowflakeObjectReference,
    ) -> list[InferredSource]:
        """What the object's own SQL selects from, checked against Snowflake.

        The legacy procedure's fallback for a column GET_LINEAGE knows
        nothing about. Every candidate must exist before it is returned, so
        an alias or a CTE name is never mistaken for a table.
        """
        key = object_key(reference)
        if not all(key):
            return []
        object_type = self._object_type(key, reference.object_type)
        for definition in self._definitions(key, object_type, ()):
            context = (definition.database or key[0], definition.schema_name or key[1])
            if reference.column_name:
                extraction = self._extract(
                    definition.sql,
                    reference.column_name,
                    key,
                    object_type,
                )
                if extraction is None:
                    continue
                return self._verified_columns(extraction.source_columns, context, key)
            tables = [
                self._resolve(name, context)
                for name in referenced_tables(definition.sql)
            ]
            return self._verified_tables(tables, key)
        return []

    # -- object kinds ---------------------------------------------------------

    def _object_type(self, key: ObjectKey, hint: str | None) -> str | None:
        database, schema_name, name = key
        listed = (self._schema_objects(database, schema_name) or {}).get(name)
        if listed is None:
            # SHOW failed, or the schema holds more than it returns. Whatever
            # GET_LINEAGE's dataset_type said is the best answer left.
            return hint
        if "VIEW" in listed.kind:
            view = (self._schema_views(database, schema_name) or {}).get(name)
            if (view is not None and view.is_materialized) or (
                hint is not None and "MATERIALIZED" in hint
            ):
                return "MATERIALIZED VIEW"
            return "VIEW"
        if listed.is_dynamic:
            return "DYNAMIC TABLE"
        if listed.is_external:
            return "EXTERNAL TABLE"
        return "TABLE"

    def _schema_objects(
        self,
        database: str,
        schema_name: str,
    ) -> dict[str, SnowflakeSchemaObject] | None:
        return self._objects.get(
            (database, schema_name),
            lambda: self._required(
                f"the objects in {database}.{schema_name}",
                lambda: self._client.show_objects(
                    self._connection,
                    database=database,
                    schema_name=schema_name,
                ),
            ),
        )

    def _schema_views(
        self,
        database: str,
        schema_name: str,
    ) -> dict[str, SnowflakeViewDefinition] | None:
        def compute() -> dict[str, SnowflakeViewDefinition]:
            views = self._required(
                f"the views in {database}.{schema_name}",
                lambda: self._client.show_views(
                    self._connection,
                    database=database,
                    schema_name=schema_name,
                ),
            )
            return {view.name: view for view in views}

        return self._views.get((database, schema_name), compute)

    def _schema_dynamic_tables(
        self,
        database: str,
        schema_name: str,
    ) -> dict[str, str | None] | None:
        return self._dynamic_tables.get(
            (database, schema_name),
            lambda: self._required(
                f"the dynamic tables in {database}.{schema_name}",
                lambda: self._client.show_dynamic_tables(
                    self._connection,
                    database=database,
                    schema_name=schema_name,
                ),
            ),
        )

    # -- definitions ----------------------------------------------------------

    def _definitions(
        self,
        key: ObjectKey,
        object_type: str | None,
        query_ids: tuple[str, ...],
    ) -> list[_Definition]:
        """The SQL that defines or loaded the object, most authoritative first.

        A view-like object has one definition. A table has the statements
        GET_LINEAGE named, newest first, then the newest statements found in
        query history. Searching is single-flight, so after build() has
        searched every table this only reads what that search found.
        """
        if _defined_by_ddl(object_type):
            ddl = self._object_ddl(key, object_type)
            return [ddl] if ddl is not None else []
        if object_type is not None and not is_loaded_table(object_type):
            return []
        statements, named = self._history_for([key], query_ids)
        records = [
            *(
                (record, "LINEAGE_PROCESS")
                for record in sorted(
                    named.values(),
                    key=lambda item: (
                        item.start_time.timestamp() if item.start_time else 0.0
                    ),
                    reverse=True,
                )
            ),
            *statements.get(key, []),
        ]
        definitions: list[_Definition] = []
        seen: set[str] = set()
        for record, source in records:
            if record.query_id in seen:
                continue
            seen.add(record.query_id)
            if len(record.query_text) >= _HISTORY_TEXT_LIMIT:
                self._notice(
                    "SNOWFLAKE_TRANSFORMATION_SQL_TRUNCATED",
                    (
                        f"Statement {record.query_id} is at least "
                        f"{_HISTORY_TEXT_LIMIT:,} characters long; query history "
                        "keeps no more, so its end may be missing."
                    ),
                    ".".join(key),
                )
            definitions.append(
                _Definition(
                    sql=record.query_text,
                    source=source,
                    database=record.database_name,
                    schema_name=record.schema_name,
                    query_id=record.query_id,
                    query_type=record.query_type,
                    modified_at=record.start_time,
                )
            )
        return definitions

    @staticmethod
    def _for_node(
        definitions: list[_Definition],
        query_ids: tuple[str, ...] | None,
    ) -> list[_Definition]:
        # A statement GET_LINEAGE named for this very column goes first; the
        # rest keep their order.
        if not query_ids:
            return definitions
        named = set(query_ids)
        return sorted(definitions, key=lambda item: item.query_id not in named)

    def _object_ddl(
        self,
        key: ObjectKey,
        object_type: str | None,
    ) -> _Definition | None:
        database, schema_name, name = key
        qualified = ".".join(key)

        def compute() -> _Definition | None:
            text: str | None = None
            if is_view_like(object_type):
                view = (self._schema_views(database, schema_name) or {}).get(name)
                if view is not None and view.is_secure and not view.text:
                    # GET_DDL and every other route hide it the same way.
                    self._notice(
                        "SNOWFLAKE_TRANSFORMATION_DEFINITION_HIDDEN",
                        (
                            f"{qualified} is a secure view; only its owner role "
                            "can read its definition."
                        ),
                        qualified,
                    )
                    return None
                text = view.text if view is not None else None
            elif is_dynamic_table(object_type):
                listed = self._schema_dynamic_tables(database, schema_name) or {}
                text = listed.get(name)
            if not text:
                # SHOW stops at 10,000 rows, and a dynamic table's text needs
                # OWNERSHIP or MONITOR; GET_DDL is the per-object fallback.
                ddl_type = (
                    "VIEW"
                    if is_view_like(object_type)
                    else "DYNAMIC_TABLE"
                    if is_dynamic_table(object_type)
                    else "TABLE"
                )
                text = self._read(
                    f"the definition of {qualified}",
                    lambda: self._client.get_ddl(
                        self._connection,
                        object_type=ddl_type,
                        database=database,
                        schema_name=schema_name,
                        object_name=name,
                    ),
                    root=qualified,
                )
            if not text:
                return None
            return _Definition(
                sql=text,
                source="OBJECT_DDL",
                database=database,
                schema_name=schema_name,
            )

        return self._ddl.get(key, compute)

    # -- query history ------------------------------------------------------

    def _history_for(
        self,
        tables: Sequence[ObjectKey],
        query_ids: Sequence[str],
    ) -> tuple[
        dict[ObjectKey, list[tuple[SnowflakeQueryRecord, str]]],
        dict[str, SnowflakeQueryRecord],
    ]:
        """Statements that wrote each table, and the statements named by id."""
        keys: list[Hashable] = [("table", key) for key in tables]
        keys.extend(("query", query_id) for query_id in query_ids)
        if not keys:
            return {}, {}
        results = self._history.get_many(keys, self._search_history)
        statements = {key: results.get(("table", key)) or [] for key in tables}
        named = {
            query_id: record
            for query_id in query_ids
            if (record := results.get(("query", query_id))) is not None
        }
        return statements, named

    def _search_history(self, missing: list[Hashable]) -> dict[Hashable, Any]:
        tables: list[ObjectKey] = [key[1] for key in missing if key[0] == "table"]
        query_ids: list[str] = [key[1] for key in missing if key[0] == "query"]
        statements: dict[ObjectKey, list[tuple[SnowflakeQueryRecord, str]]] = {
            key: [] for key in tables
        }
        named: dict[str, SnowflakeQueryRecord] = {}

        self._search_recent(tables, query_ids, statements, named)
        if self._request.search_account_usage:
            unresolved = [key for key in tables if not statements[key]]
            if unresolved:
                self._search_account_usage(unresolved, statements)
            unnamed = [query_id for query_id in query_ids if query_id not in named]
            if unnamed:
                records = self._read(
                    "the statements GET_LINEAGE named "
                    "(SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY)",
                    lambda: self._client.account_usage_queries(
                        self._connection,
                        query_ids=unnamed,
                        lookback_days=self._request.history_lookback_days,
                    ),
                )
                for record in records or []:
                    named[record.query_id] = record

        results: dict[Hashable, Any] = {
            ("table", key): value[:_STATEMENTS_PER_TABLE]
            for key, value in statements.items()
        }
        results.update(
            {("query", query_id): named.get(query_id) for query_id in query_ids}
        )
        return results

    def _search_recent(
        self,
        tables: list[ObjectKey],
        query_ids: list[str],
        statements: dict[ObjectKey, list[tuple[SnowflakeQueryRecord, str]]],
        named: dict[str, SnowflakeQueryRecord],
    ) -> None:
        wanted = set(tables)
        seen: set[str] = set()
        end_before: datetime | None = None
        for _ in range(_HISTORY_PAGES):
            pending_ids = sorted(set(query_ids) - set(named))
            patterns = sorted(
                {contains_pattern(key[2]) for key in tables if not statements[key]}
            )
            if not pending_ids and not patterns:
                return
            page = self._read(
                "recent query history (INFORMATION_SCHEMA.QUERY_HISTORY)",
                lambda: self._client.recent_history(
                    self._connection,
                    name_patterns=patterns,
                    query_ids=pending_ids,
                    database=self._history_database
                    or (tables[0][0] if tables else None),
                    end_before=end_before,
                    limit=_HISTORY_LIMIT,
                ),
            )
            if page is None:
                return
            for record in page.records:
                if record.query_id in seen:
                    continue
                seen.add(record.query_id)
                if record.query_id in query_ids:
                    named[record.query_id] = record
                target = self._statement_target(record)
                if target in wanted:
                    statements[target].append((record, "QUERY_HISTORY"))
            if (
                page.scanned < HISTORY_FUNCTION_RESULT_LIMIT
                or page.oldest_end_time is None
            ):
                # The whole 7-day window was seen.
                return
            end_before = page.oldest_end_time
        if not self._request.search_account_usage and any(
            not statements[key] for key in tables
        ):
            self._notice(
                "SNOWFLAKE_TRANSFORMATION_HISTORY_PARTIAL",
                (
                    "INFORMATION_SCHEMA.QUERY_HISTORY only reaches the most recent "
                    f"{_HISTORY_PAGES * HISTORY_FUNCTION_RESULT_LIMIT:,} statements "
                    "this role can see, back to "
                    f"{end_before.isoformat() if end_before else 'an unknown time'}; "
                    "older loads need search_account_usage."
                ),
            )

    def _search_account_usage(
        self,
        tables: list[ObjectKey],
        statements: dict[ObjectKey, list[tuple[SnowflakeQueryRecord, str]]],
    ) -> None:
        by_name = {".".join(key).upper(): key for key in tables}
        writes = self._attempt(
            lambda: self._client.access_history_writes(
                self._connection,
                qualified_names=list(by_name),
                lookback_days=self._request.history_lookback_days,
                per_table=_STATEMENTS_PER_TABLE,
            )
        )
        if writes is not None:
            for target_name, record in writes:
                key = by_name.get(target_name.upper())
                if key is not None:
                    statements[key].append((record, "ACCESS_HISTORY"))
            return

        # ACCESS_HISTORY is unreadable (edition or privileges): fall back to
        # the legacy procedure's text search, batched over every table.
        records = self._read(
            "query history (SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY)",
            lambda: self._client.account_usage_writes(
                self._connection,
                name_patterns=sorted({contains_pattern(key[2]) for key in tables}),
                lookback_days=self._request.history_lookback_days,
                limit=_HISTORY_LIMIT,
            ),
        )
        wanted = set(tables)
        for record in records or []:
            target = self._statement_target(record)
            if target in wanted:
                statements[target].append((record, "ACCOUNT_USAGE_QUERY_HISTORY"))

    @staticmethod
    def _statement_target(record: SnowflakeQueryRecord) -> ObjectKey | None:
        info = describe_statement(record.query_text)
        if info.kind not in _WRITE_STATEMENTS or info.target is None:
            return None
        # DATABASE_NAME / SCHEMA_NAME are the session's context when the
        # statement compiled: exactly what its unqualified names resolved in.
        database, schema_name, name = info.target.resolve(
            record.database_name,
            record.schema_name,
        )
        if not database or not schema_name:
            return None
        return (database, schema_name, name)

    # -- columns --------------------------------------------------------------

    def _table_columns(
        self,
        keys: Sequence[ObjectKey],
    ) -> dict[ObjectKey, tuple[SnowflakeColumnInfo, ...] | None]:
        if not keys:
            return {}
        by_schema: dict[tuple[str, str], list[ObjectKey]] = defaultdict(list)
        for key in keys:
            by_schema[(key[0], key[1])].append(key)

        def read(missing: list[Hashable]) -> dict[Hashable, Any]:
            wanted: list[ObjectKey] = list(missing)  # type: ignore[arg-type]
            database, schema_name = wanted[0][0], wanted[0][1]
            columns = self._required(
                f"the columns of {database}.{schema_name}",
                lambda: self._client.table_columns(
                    self._connection,
                    database=database,
                    schema_name=schema_name,
                    table_names=sorted({key[2] for key in wanted}),
                ),
            )
            grouped: dict[Hashable, list[SnowflakeColumnInfo]] = {
                key: [] for key in wanted
            }
            for column in columns:
                key = (database, schema_name, column.table_name)
                if key in grouped:
                    grouped[key].append(column)
            return {
                key: tuple(sorted(value, key=lambda item: item.ordinal_position))
                for key, value in grouped.items()
            }

        results: dict[ObjectKey, tuple[SnowflakeColumnInfo, ...] | None] = {}
        for schema_keys in by_schema.values():
            results.update(self._columns.get_many(schema_keys, read))
        return results

    def _verified_columns(
        self,
        sources: Sequence[SqlColumnSource],
        context: tuple[str | None, str | None],
        own: ObjectKey,
    ) -> list[InferredSource]:
        candidates = [
            (key, source)
            for source in sources
            if (key := self._resolve(source.table, context)) is not None and key != own
        ]
        columns = self._table_columns([key for key, _ in candidates])
        inferred: list[InferredSource] = []
        claimed: set[str] = set()
        for key, source in candidates:
            known = columns.get(key)
            if known is None:
                # The table could not be read; trust only an unambiguous
                # reference, never a guess between several tables.
                if not source.certain:
                    continue
            elif source.column not in {column.column_name for column in known}:
                continue
            if not source.certain:
                # An unqualified column several tables could own goes to the
                # first that has it, in FROM order, as the procedure did.
                if source.column in claimed:
                    continue
                claimed.add(source.column)
            inferred.append(
                InferredSource(
                    database=key[0],
                    schema_name=key[1],
                    object_name=key[2],
                    column_name=source.column,
                )
            )
        return list(dict.fromkeys(inferred))

    def _verified_tables(
        self,
        keys: Sequence[ObjectKey | None],
        own: ObjectKey,
    ) -> list[InferredSource]:
        candidates = [key for key in dict.fromkeys(keys) if key and key != own]
        columns = self._table_columns(candidates)
        return [
            InferredSource(database=key[0], schema_name=key[1], object_name=key[2])
            for key in candidates
            # No visible columns: it may not exist at all, or be a CTE name.
            if columns.get(key)
        ]

    @staticmethod
    def _resolve(
        name: SqlObjectName,
        context: tuple[str | None, str | None],
    ) -> ObjectKey | None:
        database, schema_name, object_name = name.resolve(context[0], context[1])
        if not database or not schema_name or not object_name:
            return None
        return (database, schema_name, object_name)

    # -- composing a node ----------------------------------------------------

    def _extract(
        self,
        sql: str,
        column: str,
        key: ObjectKey,
        object_type: str | None,
    ) -> SqlColumnTransformation | None:
        table_columns = None
        if object_type is None or is_loaded_table(object_type):
            known = self._table_columns([key]).get(key)
            if known:
                table_columns = [item.column_name for item in known]
        return extract_column_transformation(sql, column, table_columns=table_columns)

    def _transformation(
        self,
        node: SnowflakeObjectReference,
        *,
        object_type: str | None,
        definitions: list[_Definition],
        columns: tuple[SnowflakeColumnInfo, ...] | None,
        graph: TraceGraph,
    ) -> SnowflakeColumnTransformation:
        parents = sorted(
            graph.parents.get(node.object_id, ()),
            key=lambda item: (
                graph.nodes[item].qualified_name if item in graph.nodes else item
            ),
        )
        base: dict[str, Any] = {
            "object_id": node.object_id,
            "qualified_name": node.qualified_name,
            "database": node.database,
            "schema_name": node.schema_name,
            "object_name": node.object_name,
            "column_name": node.column_name,
            "object_type": object_type,
            "lineage_level": graph.levels.get(node.object_id, 0),
            "parent_object_ids": parents,
            "parent_qualified_names": [
                graph.nodes[item].qualified_name
                for item in parents
                if item in graph.nodes
            ],
        }
        column = node.column_name
        if not column:
            return self._entry(base, "OBJECT", None, definitions[:1])

        table_columns = [item.column_name for item in columns] if columns else None
        for definition in definitions:
            extraction = extract_column_transformation(
                definition.sql,
                column,
                table_columns=table_columns,
            )
            if extraction is not None:
                return self._from_extraction(base, column, extraction, definition)

        if definitions:
            if object_type is None or is_loaded_table(object_type):
                return self._entry(
                    base,
                    "INGESTION_QUERY",
                    f"{column} (not named by the statement that loaded "
                    f"{node.object_name}; see modification_sql)",
                    definitions[:1],
                )
            return self._entry(
                base, "NOT_FOUND", f"{column} (present in object)", definitions[:1]
            )

        data_type = next(
            (item.data_type for item in columns or () if item.column_name == column),
            None,
        )
        if data_type:
            return self._entry(
                base,
                "BASE_COLUMN",
                f"{column} {data_type} (base table column — no ingestion history "
                "found)",
                [],
            )
        return self._entry(
            base,
            "NO_DEFINITION",
            f"{column} (source — no transformation SQL found)",
            [],
        )

    def _from_extraction(
        self,
        base: dict[str, Any],
        column: str,
        extraction: SqlColumnTransformation,
        definition: _Definition,
    ) -> SnowflakeColumnTransformation:
        expression = extraction.expression
        if extraction.kind == "STAGE_LOAD":
            text = (
                f"{column} (loaded by COPY INTO from {extraction.stage or 'a stage'})"
            )
            kind = "STAGE_LOAD"
        elif extraction.kind == "CLONE":
            source = next(iter(extraction.source_columns), None)
            origin = ".".join(source.table.parts) if source is not None else "a table"
            text = f"{column} (cloned from {origin})"
            kind = "CLONE"
        elif extraction.kind == "PASS_THROUGH":
            reference = expression or column
            if not extraction.steps and split_identifier(reference) == (column,):
                text = f"{column} ({_DIRECT_REFERENCE_NOTE})"
                kind = "DIRECT_REFERENCE"
            else:
                text = f"{reference} (passed through from source)"
                kind = "PASS_THROUGH"
        else:
            text = expression or column
            kind = "EXPRESSION"
        return self._entry(
            base,
            kind,
            text,
            [definition],
            steps=list(extraction.steps),
            referenced=list(extraction.referenced_columns),
        )

    @staticmethod
    def _entry(
        base: dict[str, Any],
        kind: str,
        text: str | None,
        definitions: list[_Definition],
        *,
        steps: list[str] | None = None,
        referenced: list[str] | None = None,
    ) -> SnowflakeColumnTransformation:
        definition = definitions[0] if definitions else None
        sql = definition.sql if definition is not None else None
        if sql is not None and len(sql) > _MAX_SQL_CHARS:
            sql = sql[:_MAX_SQL_CHARS] + "\n-- [truncated]"
        return SnowflakeColumnTransformation(
            **base,
            column_transformation=collapse_whitespace(text) if text else None,
            transformation_kind=kind,
            transformation_steps=steps or [],
            referenced_columns=referenced or [],
            modification_sql=sql,
            modification_sql_source=definition.source if definition else None,
            modification_query_id=definition.query_id if definition else None,
            modification_query_type=definition.query_type if definition else None,
            modified_at=definition.modified_at if definition else None,
        )

    # -- plumbing ------------------------------------------------------------

    def _gather(self, tasks: Mapping[Hashable, Callable[[], Any]]) -> dict[Any, Any]:
        """Run lookups concurrently on the metadata pool; build() only."""
        futures = {key: self._executor.submit(task) for key, task in tasks.items()}
        wait(futures.values())
        results: dict[Any, Any] = {}
        for key, future in futures.items():
            try:
                results[key] = future.result()
            except Exception:  # noqa: BLE001 - each lookup already warned
                results[key] = None
        return results

    def _count(self) -> None:
        with self._count_lock:
            self._query_count += 1

    def _attempt(self, call: Callable[[], Any]) -> Any:
        """A read whose failure has a fallback, so it is not a warning."""
        self._count()
        try:
            return call()
        except Exception:  # noqa: BLE001 - the caller falls back
            return None

    def _read(
        self,
        what: str,
        call: Callable[[], Any],
        *,
        root: str | None = None,
    ) -> Any:
        self._count()
        try:
            return call()
        except Exception as error:  # noqa: BLE001 - definition reads degrade
            self._notice(
                "SNOWFLAKE_TRANSFORMATION_LOOKUP_FAILED",
                f"Could not read {what}: {_reason(error)}",
                root,
            )
            return None

    def _required(self, what: str, call: Callable[[], Any]) -> Any:
        """A read whose failure is cached: raising marks the key as failed."""
        value = self._read(what, call)
        if value is None:
            raise _LookupFailed
        return value

    def _notice(self, code: str, message: str, root: str | None = None) -> None:
        self._warn(
            SnowflakeLineageWarning(code=code, message=message, root_object_name=root)
        )


class _LookupFailed(Exception):
    """A lookup failed and has already been reported."""


def _reason(error: BaseException) -> str:
    detail = getattr(error, "message", None) or str(error)
    detail = " ".join(detail.split())
    if not detail:
        return type(error).__name__
    return detail[:_MAX_WARNING_DETAIL] + (
        "..." if len(detail) > _MAX_WARNING_DETAIL else ""
    )
