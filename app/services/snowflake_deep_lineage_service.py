import re
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from itertools import count
from threading import Lock
from typing import Any

from app.clients.snowflake_lineage_query_client import (
    SnowflakeLineageQueryClient,
)
from app.core.config import get_settings
from app.core.exceptions import ProviderAuthenticationRequiredError
from app.domain.lineage_ids import stable_lineage_id
from app.domain.snowflake_sql import split_identifier
from app.schemas.snowflake_lineage import (
    SnowflakeDeepLineageRequest,
    SnowflakeDeepLineageResponse,
    SnowflakeDependency,
    SnowflakeLineageSnapshot,
    SnowflakeLineageWarning,
    SnowflakeObjectReference,
)
from app.services.auth.snowflake_session_store import (
    SnowflakeConnection,
    SnowflakeSessionStore,
    get_snowflake_session_store,
)
from app.services.snowflake_transformation_service import (
    InferredSource,
    SnowflakeTransformationService,
    TraceGraph,
    TransformationSession,
    object_key,
    process_query_ids,
)

_SNOWFLAKE_BATCH_DEPTH = 5
_MAX_WARNING_DETAIL = 300
_MAX_WARNINGS = 500
# Table-like domains GET_LINEAGE can be re-rooted on -- always as TABLE,
# which "includes all table-like objects including views and dynamic
# tables". A STAGE or DATASET terminates the walk; a view does not.
_TABLE_LIKE_DOMAINS = frozenset({"TABLE", "VIEW", "MATERIALIZED VIEW"})
# Lineage past these cannot be read: the object was dropped, or the role
# cannot see it.
_TERMINAL_STATUSES = frozenset({"MASKED", "DELETED"})
# GET_LINEAGE reports every table-like object as TABLE, so neither domain
# says what the object really is; *_DETAILS.dataset_type does.
_COARSE_DOMAINS = frozenset({"TABLE", "COLUMN"})
_SIMPLE_IDENTIFIER = re.compile(r"^[A-Z_][A-Z0-9_$]*$")
GET_LINEAGE_DEPENDENCY = "GET_LINEAGE"
SQL_INFERRED_DEPENDENCY = "SQL_INFERRED"


@dataclass(frozen=True)
class _TraversalRoot:
    reference: SnowflakeObjectReference
    level_offset: int


@dataclass(frozen=True)
class _Task:
    sequence: int
    inference: bool
    item: _TraversalRoot


class _WarningCollector:
    """Deduplicates on the way in and stops growing at a hard cap.

    Row-level warnings are emitted per bad row, so a wide traversal could
    accumulate a warning list larger than the lineage it describes. The
    response only ever exposed the deduplicated set, so nothing is lost by
    collapsing them here instead of at the end. Definition lookups report from
    worker threads, hence the lock.
    """

    def __init__(self, max_warnings: int = _MAX_WARNINGS) -> None:
        self._max_warnings = max_warnings
        self._seen: set[tuple[str, str, str | None]] = set()
        self._warnings: list[SnowflakeLineageWarning] = []
        self._lock = Lock()
        self.overflowed = False

    def add(self, warning: SnowflakeLineageWarning) -> None:
        key = (warning.code, warning.message, warning.root_object_name)
        with self._lock:
            if key in self._seen:
                return
            if len(self._warnings) >= self._max_warnings:
                self.overflowed = True
                return
            self._seen.add(key)
            self._warnings.append(warning)

    def ordered(self) -> list[SnowflakeLineageWarning]:
        with self._lock:
            if not self.overflowed:
                return list(self._warnings)
            return [
                *self._warnings,
                SnowflakeLineageWarning(
                    code="SNOWFLAKE_LINEAGE_WARNINGS_TRUNCATED",
                    message=(
                        f"Only the first {self._max_warnings} distinct lineage "
                        "warnings are reported."
                    ),
                ),
            ]


@dataclass(frozen=True)
class _ParsedRow:
    source: SnowflakeObjectReference
    target: SnowflakeObjectReference
    distance: int
    process: dict[str, Any] | list[Any] | str | None


class SnowflakeDeepLineageService:
    def __init__(
        self,
        *,
        query_client: SnowflakeLineageQueryClient | None = None,
        store: SnowflakeSessionStore | None = None,
        transformation_service: SnowflakeTransformationService | None = None,
    ) -> None:
        settings = get_settings()
        self.query_client = query_client or SnowflakeLineageQueryClient()
        self.store = store or get_snowflake_session_store(
            settings.snowflake_session_max_age_seconds
        )
        self.transformation_service = (
            transformation_service or SnowflakeTransformationService()
        )

    def trace_session(
        self,
        session_id: str,
        request: SnowflakeDeepLineageRequest,
    ) -> SnowflakeDeepLineageResponse:
        try:
            with self.store.checkout(session_id) as session:
                return self.trace(
                    session.connection,
                    account_identifier=session.identity.account_identifier,
                    request=request,
                )
        except KeyError as exc:
            raise ProviderAuthenticationRequiredError("snowflake") from exc

    def trace(
        self,
        connection: SnowflakeConnection,
        *,
        account_identifier: str,
        request: SnowflakeDeepLineageRequest,
    ) -> SnowflakeDeepLineageResponse:
        root = self._root_reference(account_identifier, request)
        warnings = _WarningCollector()
        reads_sql = request.include_transformations or self._infers(request)
        # Two pools so definition reads never queue behind -- or in front of
        # -- the GET_LINEAGE calls that decide how far the walk goes.
        lineage_pool = ThreadPoolExecutor(
            max_workers=request.max_concurrency,
            thread_name_prefix="snowflake-lineage",
        )
        metadata_pool = (
            ThreadPoolExecutor(
                max_workers=request.max_concurrency,
                thread_name_prefix="snowflake-metadata",
            )
            if reads_sql
            else None
        )
        finished = False
        try:
            session = (
                self.transformation_service.open(
                    connection,
                    request=request,
                    executor=metadata_pool,
                    warn=warnings.add,
                )
                if metadata_pool is not None
                else None
            )
            walk = _LineageWalk(
                service=self,
                connection=connection,
                account_identifier=account_identifier,
                request=request,
                root=root,
                lineage_pool=lineage_pool,
                metadata_pool=metadata_pool,
                session=session,
                warnings=warnings,
            )
            walk.run()
            report = (
                session.build(walk.graph())
                if session is not None and request.include_transformations
                else None
            )
            finished = True
        finally:
            # On failure, do not hold the request open for queries whose
            # results can no longer be used.
            lineage_pool.shutdown(wait=finished, cancel_futures=not finished)
            if metadata_pool is not None:
                metadata_pool.shutdown(wait=finished, cancel_futures=not finished)

        object_types = report.object_types if report is not None else {}
        ordered_nodes = sorted(
            (self._typed(reference, object_types) for reference in walk.nodes.values()),
            key=lambda item: item.object_id,
        )
        ordered_edges = sorted(
            (
                edge.model_copy(
                    update={
                        "source": self._typed(edge.source, object_types),
                        "target": self._typed(edge.target, object_types),
                    }
                )
                for edge in walk.edges.values()
            ),
            key=lambda item: (
                item.distance or 0,
                item.source.qualified_name,
                item.target.qualified_name,
            ),
        )
        snapshot_warnings = warnings.ordered()
        snapshot = SnowflakeLineageSnapshot(
            account_identifier=account_identifier,
            objects=ordered_nodes,
            dependencies=ordered_edges,
            warnings=snapshot_warnings,
            object_count=len(ordered_nodes),
            dependency_count=len(ordered_edges),
        )
        assert request.object_domain is not None
        return SnowflakeDeepLineageResponse(
            account_identifier=account_identifier,
            starting_object_name=request.object_name,
            starting_column_name=request.column_name,
            object_domain=request.object_domain,
            direction=request.direction,
            max_depth=request.max_depth,
            query_count=walk.query_count,
            metadata_query_count=session.query_count if session is not None else 0,
            inferred_dependency_count=walk.inferred_count,
            truncated=walk.truncated,
            snapshot=snapshot,
            transformations=report.transformations if report is not None else [],
            warnings=snapshot_warnings,
        )

    def _query(
        self,
        connection: SnowflakeConnection,
        item: _TraversalRoot,
        request: SnowflakeDeepLineageRequest,
    ) -> tuple[int, list[dict[str, Any]]]:
        batch_depth = min(
            _SNOWFLAKE_BATCH_DEPTH,
            request.max_depth - item.level_offset,
        )
        rows = self.query_client.get_lineage(
            connection,
            object_name=item.reference.qualified_name,
            object_domain=self._query_domain(item.reference),
            direction=request.direction,
            max_distance=batch_depth,
        )
        return batch_depth, rows

    @staticmethod
    def _infers(request: SnowflakeDeepLineageRequest) -> bool:
        # Inference reads the SQL that *produced* a column, which names its
        # sources. Nothing in an object's own SQL names its consumers, so a
        # downstream trace has nothing to infer from.
        return request.infer_missing_lineage and request.direction == "UPSTREAM"

    @staticmethod
    def _typed(
        reference: SnowflakeObjectReference,
        object_types: dict[tuple[str, str, str], str],
    ) -> SnowflakeObjectReference:
        object_type = object_types.get(object_key(reference))
        if object_type is None or object_type == reference.object_type:
            return reference
        return reference.model_copy(update={"object_type": object_type})

    @staticmethod
    def _is_traversable(reference: SnowflakeObjectReference) -> bool:
        if (reference.status or "").upper() in _TERMINAL_STATUSES:
            return False
        # Anything carrying a column is queried as a COLUMN regardless of what
        # holds it, so the container's domain only gates object-level hops.
        if reference.column_name:
            return True
        return SnowflakeDeepLineageService._table_like(reference.object_domain)

    @staticmethod
    def _table_like(domain: str) -> bool:
        normalized = " ".join(domain.replace("_", " ").upper().split())
        return normalized in _TABLE_LIKE_DOMAINS or normalized.endswith(" TABLE")

    @staticmethod
    def _query_domain(reference: SnowflakeObjectReference) -> str:
        # `object_domain` on a row is the *container's* domain, but
        # `qualified_name` already carries the column. Passing the container
        # domain with a four-part name makes Snowflake read the whole string
        # as a table name and fail with "Table 'DB.SCHEMA.T.COL' does not
        # exist" -- which is what stopped every column trace at level five.
        if reference.column_name:
            return "COLUMN"
        # GET_LINEAGE accepts only TABLE for table-like objects; a VIEW
        # domain would fail as "not in the specified domain".
        if SnowflakeDeepLineageService._table_like(reference.object_domain):
            return "TABLE"
        return reference.object_domain

    @staticmethod
    def _root_reference(
        account_identifier: str,
        request: SnowflakeDeepLineageRequest,
    ) -> SnowflakeObjectReference:
        assert request.object_domain is not None
        qualified_name = request.object_name
        if request.column_name:
            qualified_name = f"{qualified_name}.{request.column_name}"
        # Unquoted names are stored upper-case, so `db.sch.orders` names the
        # object Snowflake reports as DB.SCH.ORDERS. The definition lookups
        # match on the stored name, so the root has to carry it too.
        parts = split_identifier(request.object_name)
        column_parts = split_identifier(request.column_name or "")
        root_column = column_parts[-1] if column_parts else request.column_name
        database, schema_name, object_name = (
            (parts[-3], parts[-2], parts[-1])
            if len(parts) >= 3
            else ("", "", request.object_name)
        )
        return SnowflakeDeepLineageService._reference(
            account_identifier=account_identifier,
            database=database,
            schema_name=schema_name,
            object_name=object_name,
            object_domain=request.object_domain,
            column_name=root_column,
            status="ACTIVE",
            qualified_name=qualified_name,
        )

    @staticmethod
    def _parse_row(
        account_identifier: str,
        row: dict[str, Any],
        *,
        include_process: bool,
    ) -> _ParsedRow | None:
        try:
            distance = int(row["DISTANCE"])
        except (KeyError, TypeError, ValueError):
            return None
        if distance < 1 or distance > _SNOWFLAKE_BATCH_DEPTH:
            return None

        source = SnowflakeDeepLineageService._row_reference(
            account_identifier,
            row,
            "SOURCE",
        )
        target = SnowflakeDeepLineageService._row_reference(
            account_identifier,
            row,
            "TARGET",
        )
        if source is None or target is None:
            return None
        return _ParsedRow(
            source=source,
            target=target,
            distance=distance,
            process=row.get("PROCESS") if include_process else None,
        )

    @staticmethod
    def _row_reference(
        account_identifier: str,
        row: dict[str, Any],
        prefix: str,
    ) -> SnowflakeObjectReference | None:
        values = {
            key: row.get(f"{prefix}_{key}")
            for key in (
                "OBJECT_DATABASE",
                "OBJECT_SCHEMA",
                "OBJECT_NAME",
                "OBJECT_DOMAIN",
                "COLUMN_NAME",
                "STATUS",
            )
        }
        required = (
            values["OBJECT_DATABASE"],
            values["OBJECT_SCHEMA"],
            values["OBJECT_NAME"],
            values["OBJECT_DOMAIN"],
        )
        if not all(isinstance(value, str) and value for value in required):
            return None
        column_name = values["COLUMN_NAME"]
        identifier_parts = [str(value) for value in required[:3]]
        if isinstance(column_name, str) and column_name:
            identifier_parts.append(column_name)
        qualified_name = SnowflakeDeepLineageService._qualified_identifier(
            identifier_parts
        )
        return SnowflakeDeepLineageService._reference(
            account_identifier=account_identifier,
            database=str(values["OBJECT_DATABASE"]),
            schema_name=str(values["OBJECT_SCHEMA"]),
            object_name=str(values["OBJECT_NAME"]),
            object_domain=str(values["OBJECT_DOMAIN"]),
            column_name=(column_name if isinstance(column_name, str) else None),
            status=(values["STATUS"] if isinstance(values["STATUS"], str) else None),
            qualified_name=qualified_name,
            object_type=SnowflakeDeepLineageService._object_type(
                str(values["OBJECT_DOMAIN"]),
                row.get(f"{prefix}_DETAILS"),
            ),
        )

    @staticmethod
    def _object_type(domain: str, details: Any) -> str | None:
        if isinstance(details, dict):
            for key, value in details.items():
                if str(key).casefold() == "dataset_type" and isinstance(value, str):
                    if value.strip():
                        return " ".join(value.replace("_", " ").upper().split())
        normalized = " ".join(domain.replace("_", " ").upper().split())
        if not normalized or normalized in _COARSE_DOMAINS:
            return None
        return normalized

    @staticmethod
    def _inferred_reference(
        account_identifier: str,
        source: InferredSource,
    ) -> SnowflakeObjectReference:
        parts = [source.database, source.schema_name, source.object_name]
        if source.column_name:
            parts.append(source.column_name)
        return SnowflakeDeepLineageService._reference(
            account_identifier=account_identifier,
            database=source.database,
            schema_name=source.schema_name,
            object_name=source.object_name,
            object_domain="TABLE",
            column_name=source.column_name,
            status="ACTIVE",
            qualified_name=SnowflakeDeepLineageService._qualified_identifier(parts),
            object_type=source.object_type,
        )

    @staticmethod
    def _reference(
        *,
        account_identifier: str,
        database: str,
        schema_name: str,
        object_name: str,
        object_domain: str,
        column_name: str | None,
        status: str | None,
        qualified_name: str,
        object_type: str | None = None,
    ) -> SnowflakeObjectReference:
        id_parts = [
            account_identifier,
            database,
            schema_name,
            object_name,
        ]
        if column_name:
            # A column is identified by its container and its name. Folding the
            # container's domain into the ID split the synthesised root (which
            # only knows the requested domain, COLUMN) from the same column as
            # Snowflake reports it (TABLE/VIEW), leaving the root in the
            # response as a second, edgeless node.
            id_parts.extend(("COLUMN", column_name))
        else:
            id_parts.append(object_domain)
        return SnowflakeObjectReference(
            object_id=stable_lineage_id("snowflake", *id_parts),
            database=database,
            schema_name=schema_name,
            object_name=object_name,
            object_domain=object_domain,
            column_name=column_name,
            status=status,
            qualified_name=qualified_name,
            object_type=object_type,
        )

    @staticmethod
    def _add_node(
        nodes: dict[str, SnowflakeObjectReference],
        node: SnowflakeObjectReference,
        max_nodes: int,
    ) -> bool:
        existing = nodes.get(node.object_id)
        if existing is not None:
            # The root is built from the request, so its domain is the
            # requested "COLUMN" rather than whatever actually holds the
            # column. Take Snowflake's answer once it arrives.
            if existing.object_domain == "COLUMN" and node.object_domain != "COLUMN":
                nodes[node.object_id] = node.model_copy(
                    update={"object_type": node.object_type or existing.object_type}
                )
            elif existing.object_type is None and node.object_type is not None:
                nodes[node.object_id] = existing.model_copy(
                    update={"object_type": node.object_type}
                )
            return True
        if len(nodes) >= max_nodes:
            return False
        nodes[node.object_id] = node
        return True

    @staticmethod
    def _add_edge(
        edges: dict[tuple[str, str], SnowflakeDependency],
        *,
        source: SnowflakeObjectReference,
        target: SnowflakeObjectReference,
        distance: int,
        process: dict[str, Any] | list[Any] | str | None,
        dependency_type: str,
        max_edges: int,
    ) -> bool | None:
        """True for a new edge, None for one already known, False at the cap."""
        key = (source.object_id, target.object_id)
        existing = edges.get(key)
        if existing is not None:
            if existing.distance is None or distance < existing.distance:
                existing.distance = distance
            return None
        if len(edges) >= max_edges:
            return False
        edges[key] = SnowflakeDependency(
            source=source,
            target=target,
            dependency_type=dependency_type,
            distance=distance,
            process=process,
        )
        return True

    @staticmethod
    def _reason(error: BaseException) -> str:
        # Without this the warning said only "a branch could not be read",
        # which is the same text whether the object was dropped, the role
        # lacks access, or the session died -- so nobody could act on it.
        detail = getattr(error, "message", None) or str(error)
        detail = " ".join(detail.split())
        if not detail:
            return type(error).__name__
        return detail[:_MAX_WARNING_DETAIL] + (
            "..." if len(detail) > _MAX_WARNING_DETAIL else ""
        )

    @staticmethod
    def _warning(
        code: str,
        message: str,
        root_object_name: str | None = None,
    ) -> SnowflakeLineageWarning:
        return SnowflakeLineageWarning(
            code=code,
            message=message,
            root_object_name=root_object_name,
        )

    @staticmethod
    def _qualified_identifier(parts: list[str]) -> str:
        return ".".join(
            part
            if _SIMPLE_IDENTIFIER.fullmatch(part)
            else f'"{part.replace(chr(34), chr(34) * 2)}"'
            for part in parts
        )


class _LineageWalk:
    """One trace: GET_LINEAGE calls, plus SQL inference where it has nothing.

    The walk is fed continuously instead of level by level. A boundary node
    is queried as soon as the call that found it returns, not when the
    slowest call of its level does, and an empty answer starts inference
    straight away. Only this thread mutates the graph; workers do I/O.

    Because calls finish in any order, a node can be found again at a lower
    level after it was already queried from a higher one. It is then queried
    again from the lower level, so every distance is the shortest one
    whatever order Snowflake answers in.
    """

    def __init__(
        self,
        *,
        service: SnowflakeDeepLineageService,
        connection: SnowflakeConnection,
        account_identifier: str,
        request: SnowflakeDeepLineageRequest,
        root: SnowflakeObjectReference,
        lineage_pool: ThreadPoolExecutor,
        metadata_pool: ThreadPoolExecutor | None,
        session: TransformationSession | None,
        warnings: _WarningCollector,
    ) -> None:
        self.service = service
        self.connection = connection
        self.account_identifier = account_identifier
        self.request = request
        self.root = root
        self.lineage_pool = lineage_pool
        self.metadata_pool = metadata_pool
        self.session = session
        self.warnings = warnings
        self.nodes: dict[str, SnowflakeObjectReference] = {root.object_id: root}
        self.edges: dict[tuple[str, str], SnowflakeDependency] = {}
        self.levels: dict[str, int] = {root.object_id: 0}
        self.parents: dict[str, set[str]] = defaultdict(set)
        # Node id -> statements GET_LINEAGE named as writing into it. Kept
        # even when include_process=False hides PROCESS from the response.
        self.process_queries: dict[str, list[str]] = defaultdict(list)
        self.query_count = 0
        self.inferred_count = 0
        self.truncated = False
        self._queried_at: dict[str, int] = {}
        self._inferred_from: set[str] = set()
        self._cycle_seen = False
        self._pending: dict[Future, _Task] = {}
        self._sequence = count()
        self._infers = (
            session is not None
            and metadata_pool is not None
            and SnowflakeDeepLineageService._infers(request)
        )

    def run(self) -> None:
        if self.session is not None:
            self.session.observe([self.root])
        self._query(_TraversalRoot(reference=self.root, level_offset=0))
        while self._pending:
            done, _ = wait(self._pending, return_when=FIRST_COMPLETED)
            for future in sorted(done, key=lambda item: self._pending[item].sequence):
                task = self._pending.pop(future)
                if task.inference:
                    self._absorb_inference(task.item, future)
                else:
                    self._absorb_lineage(task.item, future)

        if self._cycle_seen:
            self.warnings.add(
                self.service._warning(
                    "SNOWFLAKE_LINEAGE_CYCLE_SKIPPED",
                    (
                        "An already visited Snowflake lineage frontier "
                        "was not queried again."
                    ),
                )
            )
        if self.truncated:
            self.warnings.add(
                self.service._warning(
                    "SNOWFLAKE_LINEAGE_TRUNCATED",
                    (
                        "The lineage response reached at least one "
                        "configured safety limit."
                    ),
                )
            )

    def graph(self) -> TraceGraph:
        return TraceGraph(
            root_id=self.root.object_id,
            direction=self.request.direction,
            nodes=dict(self.nodes),
            edges=list(self.edges.values()),
            levels=dict(self.levels),
            parents={key: frozenset(value) for key, value in self.parents.items()},
            process_query_ids={
                key: tuple(dict.fromkeys(value))
                for key, value in self.process_queries.items()
            },
        )

    def _query(self, item: _TraversalRoot) -> None:
        if item.level_offset >= self.request.max_depth:
            return
        node_id = item.reference.object_id
        queried_at = self._queried_at.get(node_id)
        if queried_at is not None:
            if queried_at < item.level_offset:
                self._cycle_seen = True
            if queried_at <= item.level_offset:
                return
        if self.query_count >= self.request.max_queries:
            self.truncated = True
            self.warnings.add(
                self.service._warning(
                    "SNOWFLAKE_LINEAGE_QUERY_LIMIT_REACHED",
                    "Some lineage frontier nodes were skipped at the query limit.",
                )
            )
            return
        self._queried_at[node_id] = item.level_offset
        self.query_count += 1
        future = self.lineage_pool.submit(
            self.service._query,
            self.connection,
            item,
            self.request,
        )
        self._pending[future] = _Task(next(self._sequence), False, item)

    def _infer(self, item: _TraversalRoot) -> None:
        if not self._infers or self.metadata_pool is None or self.session is None:
            return
        if item.level_offset + 1 > self.request.max_depth:
            return
        node_id = item.reference.object_id
        if node_id in self._inferred_from:
            return
        self._inferred_from.add(node_id)
        future = self.metadata_pool.submit(
            self.session.infer_upstream,
            item.reference,
        )
        self._pending[future] = _Task(next(self._sequence), True, item)

    def _absorb_lineage(self, item: _TraversalRoot, future: Future) -> None:
        try:
            batch_depth, rows = future.result()
        except Exception as error:
            # The future only wraps the upstream call, so catching broadly here
            # is a provider boundary rather than a blanket. It has to be broad:
            # the connector raises its own exception types, and letting one
            # escape loses the whole traversal -- including every level already
            # walked -- instead of just that branch.
            if item.level_offset == 0:
                raise
            self.truncated = True
            self.warnings.add(
                self.service._warning(
                    "SNOWFLAKE_LINEAGE_BRANCH_FAILED",
                    (
                        "A non-root Snowflake lineage branch could not be "
                        f"read: {self.service._reason(error)}"
                    ),
                    item.reference.qualified_name,
                )
            )
            return

        if not rows:
            self._infer(item)
            return

        discovered: list[SnowflakeObjectReference] = []
        for raw_row in rows:
            parsed = self.service._parse_row(
                self.account_identifier,
                raw_row,
                include_process=self.request.include_process,
            )
            if parsed is None:
                self.warnings.add(
                    self.service._warning(
                        "SNOWFLAKE_LINEAGE_ROW_INVALID",
                        "Snowflake returned an incomplete lineage row.",
                        item.reference.qualified_name,
                    )
                )
                continue

            distance = item.level_offset + parsed.distance
            if distance > self.request.max_depth:
                continue
            if not self._add_node(parsed.source, discovered):
                continue
            if not self._add_node(parsed.target, discovered):
                continue
            added = self.service._add_edge(
                self.edges,
                source=parsed.source,
                target=parsed.target,
                distance=distance,
                process=parsed.process,
                dependency_type=GET_LINEAGE_DEPENDENCY,
                max_edges=self.request.max_edges,
            )
            if added is False:
                self.truncated = True
                continue

            upstream = self.request.direction == "UPSTREAM"
            far = parsed.source if upstream else parsed.target
            near = parsed.target if upstream else parsed.source
            self._place(far.object_id, distance, near.object_id)
            # Whatever the trace direction, PROCESS describes how data reached
            # the edge's target.
            self.process_queries[parsed.target.object_id].extend(
                process_query_ids(raw_row.get("PROCESS"))
            )

            if parsed.distance != batch_depth or distance >= self.request.max_depth:
                continue
            if not self.service._is_traversable(far):
                # This also dropped every VIEW, silently -- and a view is an
                # ordinary link in a column's chain.
                status = (far.status or "").upper()
                self.truncated = True
                self.warnings.add(
                    self.service._warning(
                        "SNOWFLAKE_LINEAGE_BOUNDARY_SKIPPED",
                        (
                            f"Lineage past a {status.lower()} object cannot be "
                            "followed: it was dropped, or this role cannot see it."
                            if status in _TERMINAL_STATUSES
                            else f"Lineage past a {far.object_domain} object is "
                            "not traversable."
                        ),
                        far.qualified_name,
                    )
                )
                continue
            self._query(_TraversalRoot(reference=far, level_offset=distance))

        if discovered and self.session is not None:
            self.session.observe(discovered)

    def _absorb_inference(self, item: _TraversalRoot, future: Future) -> None:
        target = item.reference
        try:
            sources: list[InferredSource] = future.result()
        except Exception as error:
            # Inference is a best-effort fallback: failing to read a
            # definition must not cost the lineage already found.
            self.warnings.add(
                self.service._warning(
                    "SNOWFLAKE_LINEAGE_INFERENCE_FAILED",
                    (
                        "Lineage could not be inferred from the object's SQL: "
                        f"{self.service._reason(error)}"
                    ),
                    target.qualified_name,
                )
            )
            return
        if not sources:
            return

        level = item.level_offset + 1
        discovered: list[SnowflakeObjectReference] = []
        inferred = 0
        for source in sources:
            reference = self.service._inferred_reference(
                self.account_identifier,
                source,
            )
            if not self._add_node(reference, discovered):
                continue
            added = self.service._add_edge(
                self.edges,
                source=reference,
                target=target,
                distance=level,
                process=None,
                dependency_type=SQL_INFERRED_DEPENDENCY,
                max_edges=self.request.max_edges,
            )
            if added is False:
                self.truncated = True
                continue
            if added:
                inferred += 1
            self._place(reference.object_id, level, target.object_id)
            self._query(_TraversalRoot(reference=reference, level_offset=level))

        if inferred:
            self.inferred_count += inferred
            self.warnings.add(
                self.service._warning(
                    "SNOWFLAKE_LINEAGE_INFERRED",
                    (
                        "Snowflake reported no lineage here, so "
                        f"{inferred} upstream "
                        f"{'source was' if inferred == 1 else 'sources were'} "
                        "read from the object's SQL instead (dependency_type "
                        f"{SQL_INFERRED_DEPENDENCY})."
                    ),
                    target.qualified_name,
                )
            )
        if discovered and self.session is not None:
            self.session.observe(discovered)

    def _add_node(
        self,
        reference: SnowflakeObjectReference,
        discovered: list[SnowflakeObjectReference],
    ) -> bool:
        known = reference.object_id in self.nodes
        if not self.service._add_node(self.nodes, reference, self.request.max_nodes):
            self.truncated = True
            return False
        if not known:
            discovered.append(reference)
        return True

    def _place(self, node_id: str, level: int, parent_id: str) -> None:
        self.levels[node_id] = min(self.levels.get(node_id, level), level)
        parent_level = max(0, level - 1)
        self.levels[parent_id] = min(
            self.levels.get(parent_id, parent_level),
            parent_level,
        )
        if node_id != parent_id:
            self.parents[node_id].add(parent_id)
