import logging
from time import perf_counter

from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

logger = logging.getLogger("app.http")


class RequestLoggingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        start_time = perf_counter()

        status_code = 500

        async def capture_response(
            message: Message,
        ) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                capture_response,
            )
        finally:
            duration_ms = round(
                (perf_counter() - start_time) * 1000,
                2,
            )

            request_id = scope.get(
                "state",
                {},
            ).get(
                "request_id",
                "unknown",
            )

            logger.info(
                "request_completed",
                extra={
                    "event": ("request_completed"),
                    "request_id": request_id,
                    "method": scope.get(
                        "method",
                        "UNKNOWN",
                    ),
                    # IMPORTANT:
                    # Path only, not query string.
                    "path": scope.get(
                        "path",
                        "",
                    ),
                    "status_code": (status_code),
                    "duration_ms": (duration_ms),
                },
            )
