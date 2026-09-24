from pydantic import BaseModel


class CacheStatusResponse(BaseModel):
    enabled: bool
    ttl_seconds: float
    max_entries: int
    entry_count: int
