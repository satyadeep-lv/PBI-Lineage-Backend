import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schemas.lineage_graph import LineageGraph
from app.schemas.lineage_persistence import (
    GraphVersionListResponse,
    GraphVersionMetadata,
    StoredLineageGraph,
)
from app.schemas.scan_job import LineageScanJob


class LineageRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_graph(self, graph: LineageGraph) -> StoredLineageGraph:
        payload = graph.model_dump(mode="json")
        content_hash = self.graph_content_hash(graph)
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                """
                SELECT version, content_hash, created_at, payload
                FROM lineage_graph_versions
                WHERE graph_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (graph.graph_id,),
            ).fetchone()

            if latest and latest["content_hash"] == content_hash:
                stored_graph = LineageGraph.model_validate_json(latest["payload"])
                return StoredLineageGraph(
                    graph=stored_graph,
                    metadata=self._metadata(graph.graph_id, latest),
                    created_new_version=False,
                )

            version = int(latest["version"]) + 1 if latest else 1
            created_at = datetime.now(UTC)
            connection.execute(
                """
                INSERT INTO lineage_graph_versions (
                    graph_id, version, content_hash, created_at, payload
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    graph.graph_id,
                    version,
                    content_hash,
                    created_at.isoformat(),
                    serialized,
                ),
            )

        return StoredLineageGraph(
            graph=graph,
            metadata=GraphVersionMetadata(
                graph_id=graph.graph_id,
                version=version,
                content_hash=content_hash,
                created_at=created_at,
            ),
            created_new_version=True,
        )

    def get_graph(
        self,
        graph_id: str,
        *,
        version: int | None = None,
    ) -> StoredLineageGraph | None:
        if version is None:
            query = """
                SELECT version, content_hash, created_at, payload
                FROM lineage_graph_versions
                WHERE graph_id = ?
                ORDER BY version DESC
                LIMIT 1
            """
            parameters: tuple[Any, ...] = (graph_id,)
        else:
            query = """
                SELECT version, content_hash, created_at, payload
                FROM lineage_graph_versions
                WHERE graph_id = ? AND version = ?
            """
            parameters = (graph_id, version)

        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()

        if row is None:
            return None
        return StoredLineageGraph(
            graph=LineageGraph.model_validate_json(row["payload"]),
            metadata=self._metadata(graph_id, row),
            created_new_version=False,
        )

    def list_graph_versions(self, graph_id: str) -> GraphVersionListResponse:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT version, content_hash, created_at
                FROM lineage_graph_versions
                WHERE graph_id = ?
                ORDER BY version DESC
                """,
                (graph_id,),
            ).fetchall()

        versions = [self._metadata(graph_id, row) for row in rows]
        return GraphVersionListResponse(
            graph_id=graph_id,
            versions=versions,
            count=len(versions),
        )

    def create_job(
        self,
        *,
        job_id: str,
        request_payload: dict[str, Any],
    ) -> LineageScanJob:
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO lineage_scan_jobs (
                    job_id, status, created_at, updated_at, request_payload
                ) VALUES (?, 'queued', ?, ?, ?)
                """,
                (
                    job_id,
                    now.isoformat(),
                    now.isoformat(),
                    json.dumps(request_payload, sort_keys=True, separators=(",", ":")),
                ),
            )
        return LineageScanJob(
            job_id=job_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )

    def update_job(
        self,
        job_id: str,
        *,
        status: str,
        result: GraphVersionMetadata | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> LineageScanJob | None:
        now = datetime.now(UTC)
        result_payload = (
            json.dumps(result.model_dump(mode="json"), separators=(",", ":"))
            if result
            else None
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE lineage_scan_jobs
                SET status = ?, updated_at = ?, result_payload = ?,
                    error_code = ?, error_message = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    now.isoformat(),
                    result_payload,
                    error_code,
                    error_message,
                    job_id,
                ),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> LineageScanJob | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT job_id, status, created_at, updated_at,
                       result_payload, error_code, error_message
                FROM lineage_scan_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None

        result = (
            GraphVersionMetadata.model_validate_json(row["result_payload"])
            if row["result_payload"]
            else None
        )
        return LineageScanJob(
            job_id=row["job_id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result=result,
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

    def fail_interrupted_jobs(self) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE lineage_scan_jobs
                SET status = 'failed', updated_at = ?,
                    error_code = 'SCAN_INTERRUPTED',
                    error_message = 'The service stopped before the scan completed.'
                WHERE status IN ('queued', 'running')
                """,
                (now,),
            )
        return cursor.rowcount

    def health_check(self) -> bool:
        with self._connect() as connection:
            result = connection.execute("SELECT 1").fetchone()
            table = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = 'lineage_graph_versions'
                """
            ).fetchone()
        return result is not None and result[0] == 1 and table is not None

    @staticmethod
    def graph_content_hash(graph: LineageGraph) -> str:
        payload = graph.model_dump(mode="json", exclude={"created_at"})
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS lineage_graph_versions (
                    graph_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (graph_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_lineage_graph_latest
                    ON lineage_graph_versions (graph_id, version DESC);

                CREATE TABLE IF NOT EXISTS lineage_scan_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    request_payload TEXT NOT NULL,
                    result_payload TEXT,
                    error_code TEXT,
                    error_message TEXT
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _metadata(graph_id: str, row: sqlite3.Row) -> GraphVersionMetadata:
        return GraphVersionMetadata(
            graph_id=graph_id,
            version=int(row["version"]),
            content_hash=row["content_hash"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
