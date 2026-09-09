import re
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import (
    reset_request_id,
    set_request_id,
)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _create_request_id(
    supplied_request_id: str | None,
) -> str:
    if supplied_request_id and _REQUEST_ID_PATTERN.fullmatch(supplied_request_id):
        return supplied_request_id

    return str(uuid4())


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
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

        request_headers = dict(scope.get("headers", []))

        raw_request_id = request_headers.get(b"x-request-id")

        supplied_request_id: str | None = None

        if raw_request_id:
            supplied_request_id = raw_request_id.decode(
                "utf-8",
                errors="ignore",
            ).strip()

        request_id = _create_request_id(supplied_request_id)

        scope.setdefault("state", {})

        scope["state"]["request_id"] = request_id

        context_token = set_request_id(request_id)

        async def send_with_request_id(
            message: Message,
        ) -> None:
            if message["type"] == "http.response.start":
                headers = list(
                    message.get(
                        "headers",
                        [],
                    )
                )

                headers.append(
                    (
                        b"x-request-id",
                        request_id.encode("utf-8"),
                    )
                )

                message["headers"] = headers

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                send_with_request_id,
            )
        finally:
            reset_request_id(context_token)
