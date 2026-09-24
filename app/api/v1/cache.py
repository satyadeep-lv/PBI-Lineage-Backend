from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies.credentials import (
    get_optional_fabric_access_token,
    get_powerbi_access_token,
)
from app.schemas.cache import CacheStatusResponse
from app.services.provider_read_cache import get_provider_read_cache

router = APIRouter()


@router.get(
    "",
    response_model=CacheStatusResponse,
)
async def get_cache_status(
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> CacheStatusResponse:
    cache = get_provider_read_cache()

    return CacheStatusResponse(
        enabled=cache.enabled,
        ttl_seconds=cache.ttl_seconds,
        max_entries=cache.max_entries,
        entry_count=len(cache),
    )


@router.delete(
    "",
    response_model=CacheStatusResponse,
)
async def clear_cache(
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
    fabric_access_token: Annotated[
        str | None,
        Depends(get_optional_fabric_access_token),
    ],
) -> CacheStatusResponse:
    """Drop this session's cached provider reads.

    Back a "Refresh" control with this. It clears only the caller's own
    entries, so one user refreshing does not evict anyone else's.
    """
    cache = get_provider_read_cache()
    cache.invalidate_session(access_token)
    # Report and semantic model definitions are fetched -- and so cached --
    # under the session's Fabric token, not its Power BI one. Without this a
    # refresh would leave every TMDL/PBIR definition stale.
    if fabric_access_token is not None:
        cache.invalidate_session(fabric_access_token)

    return CacheStatusResponse(
        enabled=cache.enabled,
        ttl_seconds=cache.ttl_seconds,
        max_entries=cache.max_entries,
        entry_count=len(cache),
    )
