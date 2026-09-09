import sqlite3

from fastapi import APIRouter, Response, status
from fastapi.responses import PlainTextResponse

from app.api.dependencies.lineage import get_lineage_repository
from app.core.config import get_settings
from app.core.metrics import metrics_registry
from app.schemas.operations import ReadinessResponse
from app.services.operations_service import OperationsService

router = APIRouter()

settings = get_settings()


@router.get("")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/live")
async def liveness_check() -> dict[str, str]:
    return {
        "status": "alive",
    }


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(response: Response) -> ReadinessResponse:
    settings = get_settings()
    try:
        repository = get_lineage_repository()
    except (OSError, sqlite3.Error):
        repository = None
    readiness = OperationsService().readiness(
        settings=settings,
        repository=repository,
    )
    if readiness.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    if not get_settings().expose_metrics:
        return PlainTextResponse("Metrics are disabled.\n", status_code=404)
    return PlainTextResponse(
        metrics_registry.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
