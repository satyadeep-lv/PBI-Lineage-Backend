import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from app.clients.snowflake_lineage_query_client import (
    SnowflakeLineageQueryClient,
)
from app.core.config import get_settings
from app.core.exceptions import ProviderAuthenticationRequiredError
from app.domain.lineage_ids import stable_lineage_id
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

_SNOWFLAKE_BATCH_DEPTH = 5
_MAX_WARNING_DETAIL = 300
# How many queries may be in flight (or finished but unread) per worker. Keeps
# the pool fed while capping how many result sets are alive at once.
_INFLIGHT_CHUNK_MULTIPLIER = 2
_MAX_WARNINGS = 500
# Domains GET_LINEAGE can be re-rooted on. A STAGE or DATASET terminates the
# walk; a view does not.
_TRAVERSABLE_DOMAINS = frozenset(
    {"TABLE", "VIEW", "MATERIALIZED VIEW", "EXTERNAL TABLE", "COLUMN"}
)
_SIMPLE_IDENTIFIER = re.compile(r"^[A-Z_][A-Z0-9_$]*$")


@dataclass(frozen=True)
class _TraversalRoot:
    reference: SnowflakeObjectReference
    level_offset: int


class _WarningCollector:
    """Deduplicates on the way in and stops growing at a hard cap.

    Row-level warnings are emitted per bad row, so a wide traversal could
    accumulate a warning list larger than the lineage it describes. The
    response only ever exposed the deduplicated set, so nothing is lost by
    collapsing them here instead of at the end.
    """

    def __init__(self, max_warnings: int = _MAX_WARNINGS) -> None:
        self._max_warnings = max_warnings
        self._seen: set[tuple[str, str, str | None]] = set()
        self._warnings: list[SnowflakeLineageWarning] = []
        self.overflowed = False

    def add(self, warning: SnowflakeLineageWarning) -> None:
        key = (warning.code, warning.message, warning.root_object_name)
        if key in self._seen:
            return
        if len(self._warnings) >= self._max_warnings:
            self.overflowed = True
            return
        self._seen.add(key)
        self._warnings.append(warning)

    def ordered(self) -> list[SnowflakeLineageWarning]:
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
    ) -> None:
        settings = get_settings()
        self.query_client = query_client or SnowflakeLineageQueryClient()
        self.store = store or get_snowflake_session_store(
            settings.snowflake_session_max_age_seconds
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
        nodes = {root.object_id: root}
        edges: dict[tuple[str, str], SnowflakeDependency] = {}
        warnings = _WarningCollector()
        frontier = [_TraversalRoot(reference=root, level_offset=0)]
        visited_roots: set[str] = set()
        query_count = 0
        truncated = False
        cycle_reported = False

        while frontier:
            pending: list[_TraversalRoot] = []
            for item in frontier:
                if item.level_offset >= request.max_depth:
                    continue
                if item.reference.object_id in visited_roots:
                    cycle_reported = True
                    continue
                visited_roots.add(item.reference.object_id)
                pending.append(item)

            remaining_queries = request.max_queries - query_count
            if remaining_queries <= 0:
                truncated = True
                warnings.add(
                    self._warning(
                        "SNOWFLAKE_LINEAGE_QUERY_LIMIT_REACHED",
                        "The configured Snowflake lineage query limit was reached.",
                    )
                )
                break
            if len(pending) > remaining_queries:
                pending = pending[:remaining_queries]
                truncated = True
                warnings.add(
                    self._warning(
                        "SNOWFLAKE_LINEAGE_QUERY_LIMIT_REACHED",
                        "Some lineage frontier nodes were skipped at the query limit.",
                    )
                )

            if not pending:
                break

            query_count += len(pending)
            next_frontier: dict[str, _TraversalRoot] = {}
            worker_count = min(request.max_concurrency, len(pending))
            chunk_size = worker_count * _INFLIGHT_CHUNK_MULTIPLIER
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                # Submit in bounded chunks. A completed future keeps its
                # rows alive until they are consumed, so submitting a whole
                # wide frontier at once held every query's result set in
                # memory at the same time.
                for start_at in range(0, len(pending), chunk_size):
                    chunk = pending[start_at : start_at + chunk_size]
                    futures = {
                        executor.submit(
                            self._query,
                            connection,
                            item,
                            request,
                        ): item
                        for item in chunk
                    }
                    for future in as_completed(futures):
                        item = futures[future]
                        try:
                            batch_depth, rows = future.result()
                        except Exception as error:
                            # The future only wraps the upstream call, so catching
                            # broadly here is a provider boundary rather than a
                            # blanket. It has to be broad: the connector raises its
                            # own exception types, and letting one escape loses the
                            # whole traversal -- including every level already
                            # walked -- instead of just that branch.
                            if item.level_offset == 0:
                                raise
                            truncated = True
                            warnings.add(
                                self._warning(
                                    "SNOWFLAKE_LINEAGE_BRANCH_FAILED",
                                    (
                                        "A non-root Snowflake lineage branch "
                                        f"could not be read: {self._reason(error)}"
                                    ),
                                    item.reference.qualified_name,
                                )
                            )
                            continue

                        for raw_row in rows:
                            parsed = self._parse_row(
                                account_identifier,
                                raw_row,
                                include_process=request.include_process,
                            )
                            if parsed is None:
                                warnings.add(
                                    self._warning(
                                        "SNOWFLAKE_LINEAGE_ROW_INVALID",
                                        "Snowflake returned an incomplete lineage row.",
                                        item.reference.qualified_name,
                                    )
                                )
                                continue

                            actual_distance = item.level_offset + parsed.distance
                            if actual_distance > request.max_depth:
                                continue

                            if not self._add_node(
                                nodes, parsed.source, request.max_nodes
                            ):
                                truncated = True
                                continue
                            if not self._add_node(
                                nodes, parsed.target, request.max_nodes
                            ):
                                truncated = True
                                continue
                            if not self._add_edge(
                                edges,
                                parsed,
                                actual_distance,
                                request.max_edges,
                            ):
                                truncated = True
                                continue

                            if (
                                parsed.distance == batch_depth
                                and actual_distance < request.max_depth
                            ):
                                boundary = (
                                    parsed.source
                                    if request.direction == "UPSTREAM"
                                    else parsed.target
                                )
                                if not self._is_traversable(boundary):
                                    # This also dropped every VIEW, silently
                                    # -- and a view is an ordinary link in a
                                    # column's chain.
                                    truncated = True
                                    warnings.add(
                                        self._warning(
                                            "SNOWFLAKE_LINEAGE_BOUNDARY_SKIPPED",
                                            (
                                                "Lineage past a "
                                                f"{boundary.object_domain} "
                                                "object is not traversable."
                                            ),
                                            boundary.qualified_name,
                                        )
                                    )
                                    continue
                                candidate = _TraversalRoot(
                                    reference=boundary,
                                    level_offset=actual_distance,
                                )
                                existing = next_frontier.get(boundary.object_id)
                                if (
                                    existing is None
                                    or candidate.level_offset < existing.level_offset
                                ):
                                    next_frontier[boundary.object_id] = candidate

                    futures.clear()
            frontier = list(next_frontier.values())

        if cycle_reported:
            warnings.add(
                self._warning(
                    "SNOWFLAKE_LINEAGE_CYCLE_SKIPPED",
                    (
                        "An already visited Snowflake lineage frontier"
                        "was not queried again."
                    ),
                )
            )
        if truncated:
            warnings.add(
                self._warning(
                    "SNOWFLAKE_LINEAGE_TRUNCATED",
                    (
                        "The lineage response reached at least one "
                        "configured safety limit."
                    ),
                )
            )

        ordered_nodes = sorted(nodes.values(), key=lambda item: item.object_id)
        ordered_edges = sorted(
            edges.values(),
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
            query_count=query_count,
            truncated=truncated,
            snapshot=snapshot,
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
    def _is_traversable(reference: SnowflakeObjectReference) -> bool:
        # Anything carrying a column is queried as a COLUMN regardless of what
        # holds it, so the container's domain only gates object-level hops.
        if reference.column_name:
            return True
        return reference.object_domain.upper() in _TRAVERSABLE_DOMAINS

    @staticmethod
    def _query_domain(reference: SnowflakeObjectReference) -> str:
        # `object_domain` on a row is the *container's* domain, but
        # `qualified_name` already carries the column. Passing the container
        # domain with a four-part name makes Snowflake read the whole string
        # as a table name and fail with "Table 'DB.SCHEMA.T.COL' does not
        # exist" -- which is what stopped every column trace at level five.
        if reference.column_name:
            return "COLUMN"
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
        parts = SnowflakeDeepLineageService._identifier_parts(request.object_name)
        column_parts = SnowflakeDeepLineageService._identifier_parts(
            request.column_name or ""
        )
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
                nodes[node.object_id] = node
            return True
        if len(nodes) >= max_nodes:
            return False
        nodes[node.object_id] = node
        return True

    @staticmethod
    def _add_edge(
        edges: dict[tuple[str, str], SnowflakeDependency],
        row: _ParsedRow,
        actual_distance: int,
        max_edges: int,
    ) -> bool:
        key = (row.source.object_id, row.target.object_id)
        existing = edges.get(key)
        if existing is not None:
            if existing.distance is None or actual_distance < existing.distance:
                existing.distance = actual_distance
            return True
        if len(edges) >= max_edges:
            return False
        edges[key] = SnowflakeDependency(
            source=row.source,
            target=row.target,
            dependency_type="GET_LINEAGE",
            distance=actual_distance,
            process=row.process,
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
    def _identifier_parts(value: str) -> list[str]:
        parts: list[str] = []
        current: list[str] = []
        quoted = False
        index = 0
        while index < len(value):
            character = value[index]
            if character == '"':
                if quoted and index + 1 < len(value) and value[index + 1] == '"':
                    current.append('"')
                    index += 2
                    continue
                quoted = not quoted
            elif character == "." and not quoted:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(character)
            index += 1
        parts.append("".join(current).strip())
        return [part for part in parts if part]

    @staticmethod
    def _qualified_identifier(parts: list[str]) -> str:
        return ".".join(
            part
            if _SIMPLE_IDENTIFIER.fullmatch(part)
            else f'"{part.replace(chr(34), chr(34) * 2)}"'
            for part in parts
        )
