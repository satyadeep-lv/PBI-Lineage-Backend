import asyncio
from typing import Any

import httpx

from app.core.exceptions import (
    InsufficientPermissionsError,
    InvalidAccessTokenError,
    ProviderResourceNotFoundError,
    UpstreamRateLimitError,
    UpstreamRequestError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from app.services.provider_read_cache import get_provider_read_cache

DEFAULT_TIMEOUT_SECONDS = 30.0

# A single pooled client for every Power BI / Fabric / scanner call. Building
# an `AsyncClient` per request made each one pay a fresh DNS lookup, TCP
# connect and TLS handshake against the same two hosts -- easily more wall
# clock than the call itself, and paid again on every poll of a long-running
# getDefinition operation.
_CONNECTION_LIMITS = httpx.Limits(
    max_connections=50,
    max_keepalive_connections=20,
    keepalive_expiry=60.0,
)
_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_provider_http_client() -> httpx.AsyncClient:
    global _client

    if _client is not None and not _client.is_closed:
        return _client

    async with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.AsyncClient(
                timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS),
                limits=_CONNECTION_LIMITS,
            )

    return _client


async def close_provider_http_client() -> None:
    global _client

    client = _client
    _client = None

    if client is not None and not client.is_closed:
        await client.aclose()


def _optional_text(
    payload: dict[str, Any],
    key: str,
) -> str | None:
    value = payload.get(key)

    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def provider_error_detail_from_payload(
    payload: dict[str, Any],
    *,
    status_code: int | None = None,
) -> str | None:
    error = payload.get("error")

    if isinstance(error, dict):
        source = error

    else:
        source = payload

    error_code = _optional_text(
        source,
        "errorCode",
    ) or _optional_text(
        source,
        "code",
    )
    message = _optional_text(
        source,
        "message",
    )

    details: list[str] = []

    if status_code is not None:
        details.append(f"Status {status_code}.")

    if error_code and message:
        details.append(f"{error_code}: {message}")

    elif error_code:
        details.append(error_code)

    elif message:
        details.append(message)

    if not details:
        return None

    return " ".join(details)


def _provider_error_detail_from_response(
    response: httpx.Response,
) -> str:
    try:
        payload = response.json()

    except ValueError:
        return f"Status {response.status_code}."

    if not isinstance(
        payload,
        dict,
    ):
        return f"Status {response.status_code}."

    return (
        provider_error_detail_from_payload(
            payload,
            status_code=response.status_code,
        )
        or f"Status {response.status_code}."
    )


def _handle_provider_response(
    *,
    response: httpx.Response,
    provider: str,
    not_found_resource: str | None = None,
) -> None:
    if response.is_success:
        return

    if response.status_code == 401:
        raise InvalidAccessTokenError(provider)

    if response.status_code == 403:
        raise InsufficientPermissionsError(provider)

    if response.status_code == 404 and not_found_resource:
        raise ProviderResourceNotFoundError(
            provider=provider,
            resource=not_found_resource,
        )

    if response.status_code == 429:
        raise UpstreamRateLimitError(
            provider=provider,
            retry_after=response.headers.get("Retry-After"),
        )

    if response.status_code >= 500:
        raise UpstreamUnavailableError(provider)

    raise UpstreamRequestError(
        provider,
        detail=(_provider_error_detail_from_response(response)),
    )


async def _provider_request(
    *,
    method: str,
    provider: str,
    url: str,
    access_token: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    additional_headers: dict[str, str] | None = None,
    not_found_resource: str | None = None,
) -> httpx.Response:
    headers = {
        "Authorization": (f"Bearer {access_token}"),
        "Accept": "application/json",
    }

    if additional_headers:
        headers.update(additional_headers)

    request_kwargs: dict[
        str,
        Any,
    ] = {
        "headers": headers,
        "params": params,
    }

    if json_body is not None:
        request_kwargs["json"] = json_body

    client = await get_provider_http_client()

    try:
        response = await client.request(
            method=method,
            url=url,
            **request_kwargs,
        )

    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(provider) from exc

    except httpx.RequestError as exc:
        raise UpstreamUnavailableError(provider) from exc

    _handle_provider_response(
        response=response,
        provider=provider,
        not_found_resource=(not_found_resource),
    )

    return response


async def provider_get(
    *,
    provider: str,
    url: str,
    access_token: str,
    params: dict[str, Any] | None = None,
    additional_headers: dict[str, str] | None = None,
    not_found_resource: str | None = None,
    cacheable: bool = False,
) -> httpx.Response:
    # Caching is opt-in per call site rather than on by default: most GETs
    # here are safe to replay, but polling a long-running operation or
    # validating a connection must always reach the provider, and a cached
    # "still running" would never resolve.
    if not cacheable:
        return await _provider_request(
            method="GET",
            provider=provider,
            url=url,
            access_token=access_token,
            params=params,
            additional_headers=additional_headers,
            not_found_resource=(not_found_resource),
        )

    cache = get_provider_read_cache()
    key = (
        cache.fingerprint(access_token),
        provider,
        url,
        _canonical_params(params),
    )

    return await cache.get_or_fetch(
        key,
        lambda: _provider_request(
            method="GET",
            provider=provider,
            url=url,
            access_token=access_token,
            params=params,
            additional_headers=additional_headers,
            not_found_resource=(not_found_resource),
        ),
    )


def _canonical_params(params: dict[str, Any] | None) -> str:
    if not params:
        return ""
    return "&".join(f"{key}={params[key]}" for key in sorted(params))


async def provider_post(
    *,
    provider: str,
    url: str,
    access_token: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    additional_headers: dict[str, str] | None = None,
    not_found_resource: str | None = None,
) -> httpx.Response:
    return await _provider_request(
        method="POST",
        provider=provider,
        url=url,
        access_token=access_token,
        params=params,
        json_body=json_body,
        additional_headers=additional_headers,
        not_found_resource=(not_found_resource),
    )
