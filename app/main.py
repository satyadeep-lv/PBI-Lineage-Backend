from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import MetricsMiddleware
from app.core.request_id import RequestIDMiddleware
from app.core.request_logging import RequestLoggingMiddleware
from app.core.security import (
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.services.auth.snowflake_session_store import (
    close_snowflake_session_store,
)

settings = get_settings()

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        close_snowflake_session_store()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.enable_api_docs else None,
        redoc_url="/redoc" if settings.enable_api_docs else None,
        openapi_url="/openapi.json" if settings.enable_api_docs else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=(
            bool(settings.cors_allowed_origins)
            and "*" not in settings.cors_allowed_origins
        ),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Lineage-Admin-Key",
            "X-Request-ID",
        ],
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )

    if settings.force_https:
        app.add_middleware(HTTPSRedirectMiddleware)

    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=settings.max_request_body_bytes,
    )

    app.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=settings.force_https,
    )

    app.add_middleware(MetricsMiddleware)

    app.add_middleware(
        RequestLoggingMiddleware,
    )

    app.add_middleware(
        RequestIDMiddleware,
    )

    register_exception_handlers(app)

    app.include_router(
        api_router,
        prefix=settings.api_v1_prefix,
    )

    return app


app = create_app()
