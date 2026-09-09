import logging

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.exceptions import (
    RequestValidationError,
)
from fastapi.responses import (
    JSONResponse,
)
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)

from app.core.exceptions import (
    AppException,
)

logger = logging.getLogger("app.errors")


def _get_request_id(
    request: Request,
) -> str:
    return getattr(
        request.state,
        "request_id",
        "unknown",
    )


async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    request_id = _get_request_id(request)

    logger.warning(
        "application_request_failed",
        extra={
            "event": ("application_request_failed"),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": (exc.status_code),
            "provider": exc.provider,
            "error_code": exc.code,
        },
    )

    headers: dict[str, str] = {}

    if exc.retry_after:
        headers["Retry-After"] = exc.retry_after

    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "provider": exc.provider,
                "request_id": request_id,
            }
        },
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    request_id = _get_request_id(request)

    logger.warning(
        "request_validation_failed",
        extra={
            "event": ("request_validation_failed"),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": 422,
            "error_code": ("REQUEST_VALIDATION_ERROR"),
        },
    )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": ("REQUEST_VALIDATION_ERROR"),
                "message": ("Request validation failed."),
                "provider": None,
                "request_id": request_id,
            }
        },
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    request_id = _get_request_id(request)

    logger.warning(
        "http_request_failed",
        extra={
            "event": "http_request_failed",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": (exc.status_code),
            "error_code": "HTTP_ERROR",
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "provider": None,
                "request_id": request_id,
            }
        },
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    request_id = _get_request_id(request)

    logger.exception(
        "unhandled_application_error",
        extra={
            "event": ("unhandled_application_error"),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
            "error_code": ("INTERNAL_SERVER_ERROR"),
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": ("INTERNAL_SERVER_ERROR"),
                "message": ("An unexpected server error occurred."),
                "provider": None,
                "request_id": request_id,
            }
        },
    )


def register_exception_handlers(
    app: FastAPI,
) -> None:
    app.add_exception_handler(
        AppException,
        app_exception_handler,
    )

    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )

    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,
    )

    app.add_exception_handler(
        Exception,
        unexpected_exception_handler,
    )
