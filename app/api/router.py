from fastapi import APIRouter

from app.api.v1 import (
    auth,
    explorer,
    gateways,
    health,
    lineage,
    reports,
    scanner,
    snowflake_auth,
    workspaces,
)

api_router = APIRouter()

api_router.include_router(
    health.router,
    prefix="/health",
    tags=["Health"],
)

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)

api_router.include_router(
    snowflake_auth.router,
    prefix="/auth/snowflake",
    tags=["Authentication"],
)

api_router.include_router(
    workspaces.router,
    prefix="/workspaces",
    tags=["Workspaces"],
)

api_router.include_router(
    reports.router,
    prefix="/reports",
    tags=["Reports"],
)

api_router.include_router(
    gateways.router,
    prefix="/gateways",
    tags=["Gateways"],
)

api_router.include_router(
    explorer.router,
    prefix="/explorer",
    tags=["Explorer"],
)

api_router.include_router(
    scanner.router,
    prefix="/scanner",
    tags=["Scanner"],
)

api_router.include_router(
    lineage.router,
    prefix="/lineage",
    tags=["Lineage"],
)
