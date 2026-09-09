import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.domain.graph_algorithms import strongly_connected_components
from app.repositories.lineage_repository import LineageRepository
from app.schemas.lineage_graph import (
    LineageEdge,
    LineageGraph,
    LineageGraphBuildRequest,
    LineageNode,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.scan_job import LineageScanJobRequest, LiveLineageScanRequest
from app.services.lineage_change_service import LineageChangeService
from app.services.lineage_search_service import (
    LineageNavigationService,
    LineageSearchService,
)
from app.services.lineage_store_service import LineageStoreService
from app.services.lineage_validation_service import LineageValidationService
from app.services.scan_job_service import LineageScanJobManager
from app.services.ttl_cache import TTLCache


def _graph(*, label: str = "Sales") -> LineageGraph:
    source = LineageNode(
        node_id="source-1",
        node_type="physical_source",
        name="Orders",
        qualified_name="warehouse.dbo.Orders",
        properties={"label": label},
    )
    table = LineageNode(
        node_id="table-1",
        node_type="semantic_table",
        name="Sales",
        qualified_name="Sales",
    )
    edge = LineageEdge(
        edge_id="edge-1",
        source_id=source.node_id,
        target_id=table.node_id,
        edge_type="populates",
    )
    return LineageGraph(
        graph_id="graph-1",
        created_at=datetime.now(UTC),
        nodes=[source, table],
        edges=[edge],
        node_count=2,
        edge_count=1,
    )


def test_repository_versions_only_changed_graphs(tmp_path):
    repository = LineageRepository(tmp_path / "lineage.db")

    first = repository.save_graph(_graph())
    unchanged = repository.save_graph(
        _graph().model_copy(
            update={"created_at": datetime.now(UTC) + timedelta(days=1)}
        )
    )
    second = repository.save_graph(_graph(label="Revenue"))

    assert first.metadata.version == 1
    assert unchanged.created_new_version is False
    assert unchanged.metadata.version == 1
    assert second.metadata.version == 2
    assert repository.list_graph_versions("graph-1").count == 2


def test_change_detection_reports_changed_node(tmp_path):
    repository = LineageRepository(tmp_path / "lineage.db")
    first = repository.save_graph(_graph())
    second = repository.save_graph(_graph(label="Revenue"))

    changes = LineageChangeService().compare(
        graph_id="graph-1",
        from_version=first.metadata.version,
        from_graph=first.graph,
        to_version=second.metadata.version,
        to_graph=second.graph,
    )

    assert changes.has_changes is True
    assert changes.changed_node_ids == ["source-1"]


def test_ttl_cache_expires_and_evicts_oldest_entry():
    current = [10.0]
    cache = TTLCache[str, str](
        ttl_seconds=5.0,
        max_entries=2,
        clock=lambda: current[0],
    )
    cache.set("one", "1")
    cache.set("two", "2")
    cache.set("three", "3")

    assert cache.get("one") is None
    assert cache.get("two") == "2"
    current[0] = 16.0
    assert cache.get("two") is None


def test_lineage_store_populates_an_initially_empty_cache(tmp_path, monkeypatch):
    repository = LineageRepository(tmp_path / "lineage.db")
    cache = TTLCache[tuple[str, int | None], object](
        ttl_seconds=30.0,
        max_entries=10,
    )
    store = LineageStoreService(repository, cache=cache)
    stored = store.save(_graph())
    monkeypatch.setattr(
        repository,
        "get_graph",
        lambda *args, **kwargs: pytest.fail("repository cache miss"),
    )

    result = store.get("graph-1")

    assert result == stored
    assert len(cache) == 2


def test_search_and_navigation_use_canonical_graph():
    graph = _graph()

    search = LineageSearchService().search(graph, query="orders")
    navigation = LineageNavigationService().navigate(
        graph,
        node_id="source-1",
        direction="downstream",
    )

    assert search.total == 1
    assert search.results[0].node.node_id == "source-1"
    assert navigation.graph.node_count == 2
    assert navigation.graph.edge_count == 1


def test_validation_rejects_missing_edge_endpoint():
    graph = _graph()
    graph.edges[0].target_id = "missing-node"

    result = LineageValidationService().validate(graph)

    assert result.valid is False
    assert result.error_count == 1
    assert result.issues[0].code == "EDGE_ENDPOINT_MISSING"


def test_cycle_detection_handles_deep_graph_without_recursion():
    adjacency = {str(index): {str(index + 1)} for index in range(2000)}
    adjacency["2000"] = {"1000"}

    components = strongly_connected_components(adjacency)

    assert any(len(component) == 1001 for component in components)


@pytest.mark.asyncio
async def test_scan_job_builds_and_persists_graph(tmp_path):
    repository = LineageRepository(tmp_path / "lineage.db")
    store = LineageStoreService(repository)
    manager = LineageScanJobManager(store, max_concurrency=1)
    request = LineageScanJobRequest(
        graph=LineageGraphBuildRequest(
            semantic_model=ParsedSemanticModelResponse(
                workspace_id="workspace-1",
                semantic_model_id="model-1",
                tables=[ParsedSemanticModelTable(name="Sales")],
            )
        )
    )

    submitted = await manager.submit(request)
    completed = None
    for _ in range(100):
        completed = await manager.get(submitted.job_id)
        if completed and completed.status in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.01)

    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.result is not None
    assert repository.get_graph(completed.result.graph_id) is not None


@pytest.mark.asyncio
async def test_live_scan_job_never_persists_provider_tokens(tmp_path):
    repository = LineageRepository(tmp_path / "lineage.db")
    manager = LineageScanJobManager(LineageStoreService(repository))
    manager.live_scan_service.build_graph = AsyncMock(return_value=_graph())
    request = LiveLineageScanRequest(
        semantic_model_workspace_id="workspace-1",
        semantic_model_id="model-1",
    )

    submitted = await manager.submit_live(
        request,
        fabric_access_token="fabric-secret-token",
        powerbi_access_token="powerbi-secret-token",
    )
    for _ in range(100):
        completed = await manager.get(submitted.job_id)
        if completed and completed.status in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.01)

    with sqlite3.connect(repository.database_path) as connection:
        payload = connection.execute(
            "SELECT request_payload FROM lineage_scan_jobs WHERE job_id = ?",
            (submitted.job_id,),
        ).fetchone()[0]

    assert "fabric-secret-token" not in payload
    assert "powerbi-secret-token" not in payload
    assert completed is not None
    assert completed.status == "succeeded"
