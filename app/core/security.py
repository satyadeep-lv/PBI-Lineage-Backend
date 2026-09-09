import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        enable_hsts: bool = False,
    ) -> None:
        self.app = app
        self.enable_hsts = enable_hsts

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                additions = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"permissions-policy": (
                        b"camera=(), microphone=(), geolocation=()"
                    ),
                    b"content-security-policy": b"frame-ancestors 'none'",
                    b"cache-control": b"no-store",
                }
                if self.enable_hsts:
                    additions[b"strict-transport-security"] = (
                        b"max-age=31536000; includeSubDomains"
                    )
                for key, value in additions.items():
                    if key not in existing:
                        headers.append((key, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_bytes:
            await self._reject(scope, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await self._reject(scope, send)

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for key, value in scope.get("headers", []):
            if key.lower() != b"content-length":
                continue
            try:
                return int(value)
            except ValueError:
                return None
        return None

    async def _reject(self, scope: Scope, send: Send) -> None:
        request_id = scope.get("state", {}).get("request_id", "unknown")
        payload = json.dumps(
            {
                "error": {
                    "code": "REQUEST_BODY_TOO_LARGE",
                    "message": "Request body exceeds the configured limit.",
                    "provider": None,
                    "request_id": request_id,
                }
            },
            separators=(",", ":"),
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})


class _RequestBodyTooLarge(Exception):
    pass
