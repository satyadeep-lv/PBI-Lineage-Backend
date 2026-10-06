"""Read a Fabric item definition and decode its JSON parts.

Every Fabric ``getDefinition`` call has the same shape: a POST that either
answers at once (200) or starts a long-running operation (202) that has to be
polled, and a result whose parts are base64 payloads. Org apps and org app
audiences only carry JSON parts (``definition.json``, ``.platform``), so this
returns them already parsed.
"""

import asyncio
import base64
import binascii
import json
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

import httpx

from app.clients.fabric_client import FabricClient
from app.clients.provider_http_client import provider_error_detail_from_payload
from app.core.exceptions import (
    UpstreamInvalidResponseError,
    UpstreamRequestError,
    UpstreamTimeoutError,
)
from app.services.provider_read_cache import get_provider_read_cache

MAX_DECODED_PART_BYTES = 10 * 1024 * 1024


class FabricItemDefinitionReader:
    DEFAULT_RETRY_AFTER_SECONDS = 2

    MAX_TOTAL_WAIT_SECONDS = 120

    def __init__(self, client: FabricClient | None = None) -> None:
        self.client = client or FabricClient()

    async def read_json_parts(
        self,
        *,
        cache_key: tuple[str, ...],
        start: Callable[[], Awaitable[httpx.Response]],
        access_token: str,
    ) -> dict[str, Any]:
        """Parsed JSON parts keyed by part path, cached per session.

        The key is namespaced under the caller's token, like every other
        provider read, so a definition is never replayed to another principal.
        """
        cache = get_provider_read_cache()
        key = (
            cache.fingerprint(access_token),
            "fabric",
            "item-definition",
            *cache_key,
        )

        return await cache.get_or_fetch(
            key,
            lambda: self._fetch(start=start, access_token=access_token),
        )

    async def _fetch(
        self,
        *,
        start: Callable[[], Awaitable[httpx.Response]],
        access_token: str,
    ) -> dict[str, Any]:
        response = await start()

        if response.status_code == 200:
            payload = _parse_object(response)
        elif response.status_code == 202:
            payload = await self._wait(
                initial_response=response,
                access_token=access_token,
            )
        else:
            raise UpstreamInvalidResponseError("fabric")

        return decode_json_parts(payload)

    async def _wait(
        self,
        *,
        initial_response: httpx.Response,
        access_token: str,
    ) -> dict[str, Any]:
        operation_id = initial_response.headers.get("x-ms-operation-id")
        if not operation_id:
            raise UpstreamInvalidResponseError("fabric")

        deadline = monotonic() + self.MAX_TOTAL_WAIT_SECONDS
        retry_after = self._retry_after(initial_response)

        while True:
            remaining = deadline - monotonic()
            if remaining <= 0 or retry_after > remaining:
                raise UpstreamTimeoutError("fabric")

            await asyncio.sleep(retry_after)

            state_response = await self.client.get_operation_state(
                operation_id=operation_id,
                access_token=access_token,
            )
            state = _parse_object(state_response)
            status = state.get("status")

            if status == "Succeeded":
                return _parse_object(
                    await self.client.get_operation_result(
                        operation_id=operation_id,
                        access_token=access_token,
                    )
                )
            if status == "Failed":
                raise UpstreamRequestError(
                    "fabric",
                    detail=provider_error_detail_from_payload(state),
                )
            if not isinstance(status, str):
                raise UpstreamInvalidResponseError("fabric")

            retry_after = self._retry_after(state_response)

    def _retry_after(self, response: httpx.Response) -> int:
        try:
            value = int(response.headers.get("Retry-After", ""))
        except ValueError:
            return self.DEFAULT_RETRY_AFTER_SECONDS
        return value if value >= 1 else self.DEFAULT_RETRY_AFTER_SECONDS


def decode_json_parts(payload: dict[str, Any]) -> dict[str, Any]:
    definition = payload.get("definition")
    parts = definition.get("parts") if isinstance(definition, dict) else None
    if not isinstance(parts, list):
        raise UpstreamInvalidResponseError("fabric")

    decoded: dict[str, Any] = {}
    for part in parts:
        if not isinstance(part, dict):
            raise UpstreamInvalidResponseError("fabric")
        path = part.get("path")
        encoded = part.get("payload")
        if not isinstance(path, str) or not isinstance(encoded, str):
            raise UpstreamInvalidResponseError("fabric")
        if not (path.endswith(".json") or path.endswith(".platform")):
            continue
        if part.get("payloadType") != "InlineBase64":
            raise UpstreamInvalidResponseError("fabric")

        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise UpstreamInvalidResponseError("fabric") from exc
        if len(raw) > MAX_DECODED_PART_BYTES:
            raise UpstreamInvalidResponseError("fabric")

        try:
            decoded[path] = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise UpstreamInvalidResponseError("fabric") from exc

    return decoded


def _parse_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamInvalidResponseError("fabric") from exc
    if not isinstance(payload, dict):
        raise UpstreamInvalidResponseError("fabric")
    return payload
