import sqlite3

from app.core.config import Settings
from app.repositories.lineage_repository import LineageRepository
from app.schemas.operations import ReadinessCheck, ReadinessResponse


class OperationsService:
    def readiness(
        self,
        *,
        settings: Settings,
        repository: LineageRepository | None,
    ) -> ReadinessResponse:
        checks: dict[str, ReadinessCheck] = {}

        if repository is None:
            checks["lineage_database"] = ReadinessCheck(
                status="fail",
                message="Lineage persistence could not be initialized.",
            )
        else:
            try:
                database_ready = repository.health_check()
            except (OSError, sqlite3.Error):
                database_ready = False
            checks["lineage_database"] = ReadinessCheck(
                status="pass" if database_ready else "fail",
                message=(
                    "Lineage persistence is available."
                    if database_ready
                    else "Lineage persistence is unavailable."
                ),
            )

        production = settings.environment.casefold() == "production"
        wildcard_cors = "*" in settings.cors_allowed_origins
        if production and wildcard_cors:
            checks["cors"] = ReadinessCheck(
                status="fail",
                message="Wildcard CORS is not allowed in production.",
            )
        else:
            checks["cors"] = ReadinessCheck(
                status="pass" if not wildcard_cors else "warn",
                message=(
                    "CORS origins are explicit or disabled."
                    if not wildcard_cors
                    else "Wildcard CORS is enabled outside production."
                ),
            )

        if production and not settings.auth_cookie_secure:
            checks["secure_cookie"] = ReadinessCheck(
                status="fail",
                message="Secure authentication cookies are required in production.",
            )
        else:
            checks["secure_cookie"] = ReadinessCheck(
                status="pass",
                message="Authentication cookie policy is valid for this environment.",
            )

        unrestricted_hosts = not settings.allowed_hosts or "*" in settings.allowed_hosts
        if production and unrestricted_hosts:
            checks["trusted_hosts"] = ReadinessCheck(
                status="fail",
                message="Explicit trusted hosts are required in production.",
            )
        else:
            checks["trusted_hosts"] = ReadinessCheck(
                status="pass" if not unrestricted_hosts else "warn",
                message=(
                    "Trusted hosts are explicitly configured."
                    if not unrestricted_hosts
                    else "Trusted hosts are unrestricted outside production."
                ),
            )

        if production and settings.lineage_admin_api_key is None:
            checks["lineage_api_key"] = ReadinessCheck(
                status="fail",
                message="A lineage administration API key is required in production.",
            )
        else:
            checks["lineage_api_key"] = ReadinessCheck(
                status=(
                    "pass" if settings.lineage_admin_api_key is not None else "warn"
                ),
                message=(
                    "Lineage administration endpoints require an API key."
                    if settings.lineage_admin_api_key is not None
                    else "Lineage administration API key enforcement is disabled."
                ),
            )

        ready = not any(check.status == "fail" for check in checks.values())
        return ReadinessResponse(
            status="ready" if ready else "not_ready",
            checks=checks,
        )
