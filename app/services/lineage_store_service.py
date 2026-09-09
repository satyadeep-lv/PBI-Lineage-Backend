from app.repositories.lineage_repository import LineageRepository
from app.schemas.lineage_graph import LineageGraph
from app.schemas.lineage_persistence import (
    GraphVersionListResponse,
    StoredLineageGraph,
)
from app.services.ttl_cache import TTLCache


class LineageStoreService:
    def __init__(
        self,
        repository: LineageRepository,
        *,
        cache: TTLCache[tuple[str, int | None], StoredLineageGraph] | None = None,
    ) -> None:
        self.repository = repository
        self.cache = cache

    def save(self, graph: LineageGraph) -> StoredLineageGraph:
        stored = self.repository.save_graph(graph)
        if self.cache is not None:
            self.cache.invalidate(lambda key: key[0] == graph.graph_id)
            self.cache.set((graph.graph_id, stored.metadata.version), stored)
            self.cache.set((graph.graph_id, None), stored)
        return stored

    def get(
        self,
        graph_id: str,
        *,
        version: int | None = None,
    ) -> StoredLineageGraph | None:
        key = (graph_id, version)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        stored = self.repository.get_graph(graph_id, version=version)
        if stored is not None and self.cache is not None:
            self.cache.set(key, stored)
        return stored

    def versions(self, graph_id: str) -> GraphVersionListResponse:
        return self.repository.list_graph_versions(graph_id)
