from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PBI Lineage Backend"
    app_version: str = "0.1.0"
    environment: str = "development"

    api_v1_prefix: str = "/api/v1"

    log_level: str = "INFO"

    xmla_tenant_name: str = "myorg"
    xmla_provider: str = "MSOLAP"

    lineage_database_path: str = "data/lineage.db"
    lineage_cache_ttl_seconds: float = Field(default=30.0, ge=0.0)
    lineage_cache_max_entries: int = Field(default=128, ge=1)
    lineage_scan_max_concurrency: int = Field(default=2, ge=1, le=32)
    snowflake_session_max_age_seconds: int = Field(
        default=45 * 60,
        ge=60,
        le=24 * 60 * 60,
    )
    snowflake_allow_external_browser_auth: bool = False

    cors_allowed_origins: list[str] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=lambda: ["*"])
    force_https: bool = False
    enable_api_docs: bool = True
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    max_request_body_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
    )
    lineage_admin_api_key: SecretStr | None = None
    expose_metrics: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
