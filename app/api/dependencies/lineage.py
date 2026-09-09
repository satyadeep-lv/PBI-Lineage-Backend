from functools import lru_cache

from app.core.config import get_settings
from app.repositories.lineage_repository import LineageRepository
from app.schemas.lineage_persistence import StoredLineageGraph
from app.services.lineage_store_service import LineageStoreService
from app.services.scan_job_service import LineageScanJobManager
from app.services.ttl_cache import TTLCache


@lru_cache
def get_lineage_repository() -> LineageRepository:
    return LineageRepository(get_settings().lineage_database_path)


@lru_cache
def get_lineage_store() -> LineageStoreService:
    settings = get_settings()
    cache = TTLCache[tuple[str, int | None], StoredLineageGraph](
        ttl_seconds=settings.lineage_cache_ttl_seconds,
        max_entries=settings.lineage_cache_max_entries,
    )
    return LineageStoreService(get_lineage_repository(), cache=cache)


@lru_cache
def get_lineage_scan_manager() -> LineageScanJobManager:
    return LineageScanJobManager(
        get_lineage_store(),
        max_concurrency=get_settings().lineage_scan_max_concurrency,
    )
