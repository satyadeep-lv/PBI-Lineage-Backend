import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from app.clients.snowflake_lineage_query_client import (
    SnowflakeLineageQueryClient,
)
from app.core.config import get_settings
from app.core.exceptions import AppException, ProviderAuthenticationRequiredError
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
_SIMPLE_IDENTIFIER = re.compile(r"^[A-Z_][A-Z0-9_$]*$")


@dataclass(frozen=True)
class _TraversalRoot:
    reference: SnowflakeObjectReference
    level_offset: int


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
        warnings: list[SnowflakeLineageWarning] = []
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
                warnings.append(
                    self._warning(
                        "SNOWFLAKE_LINEAGE_QUERY_LIMIT_REACHED",
                        "The configured Snowflake lineage query limit was reached.",
                    )
                )
                break
            if len(pending) > remaining_queries:
                pending = pending[:remaining_queries]
                truncated = True
                warnings.append(
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
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(
                        self._query,
                        connection,
                        item,
                        request,
                    ): item
                    for item in pending
                }
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        batch_depth, rows = future.result()
                    except AppException:
                        if item.level_offset == 0:
                            raise
                        truncated = True
                        warnings.append(
                            self._warning(
                                "SNOWFLAKE_LINEAGE_BRANCH_FAILED",
                                (
                                    "A non-root Snowflake lineage branch "
                                    "could not be read."
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
                            warnings.append(
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

                        if not self._add_node(nodes, parsed.source, request.max_nodes):
                            truncated = True
                            continue
                        if not self._add_node(nodes, parsed.target, request.max_nodes):
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
                            if boundary.object_domain not in {"TABLE", "COLUMN"}:
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

            frontier = list(next_frontier.values())

        if cycle_reported:
            warnings.append(
                self._warning(
                    "SNOWFLAKE_LINEAGE_CYCLE_SKIPPED",
                    (
                        "An already visited Snowflake lineage frontier"
                        "was not queried again."
                    ),
                )
            )
        if truncated:
            warnings.append(
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
        snapshot_warnings = list(
            {
                (warning.code, warning.message, warning.root_object_name): warning
                for warning in warnings
            }.values()
        )
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
            object_domain=item.reference.object_domain,
            direction=request.direction,
            max_distance=batch_depth,
        )
        return batch_depth, rows

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
            object_domain,
        ]
        if column_name:
            id_parts.append(column_name)
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
        if node.object_id in nodes:
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
