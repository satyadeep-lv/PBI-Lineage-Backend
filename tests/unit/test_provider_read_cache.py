import asyncio

import httpx
import pytest

from app.clients.powerbi_client import PowerBIClient
from app.clients.provider_http_client import provider_get
from app.services.provider_read_cache import (
    ProviderReadCache,
    get_provider_read_cache,
)


def _workspaces_payload():
    return {"value": [{"id": "workspace-1", "name": "POC", "type": "Workspace"}]}


class _CountingTransport:
    """Stands in for the network so we can count what actually goes out."""

    def __init__(self, payload=None, status_code=200):
        self.payload = payload if payload is not None else _workspaces_payload()
        self.status_code = status_code
        self.calls = 0

    async def request(self, *, method, url, **kwargs):
        self.calls += 1
        return httpx.Response(self.status_code, json=self.payload)


@pytest.fixture
def transport(monkeypatch):
    fake = _CountingTransport()

    async def _client():
        return fake

    monkeypatch.setattr(
        "app.clients.provider_http_client.get_provider_http_client",
        _client,
    )
    return fake


@pytest.mark.asyncio
async def test_a_cacheable_read_hits_the_provider_once(transport):
    for _ in range(4):
        response = await provider_get(
            provider="powerbi",
            url="https://api.powerbi.com/v1.0/myorg/groups",
            access_token="token-a",
            cacheable=True,
        )
        assert response.json() == _workspaces_payload()

    assert transport.calls == 1


@pytest.mark.asyncio
async def test_an_uncacheable_read_always_hits_the_provider(transport):
    # Operation polling and connection validation go through this path; a
    # cached "still running" would never resolve.
    for _ in range(3):
        await provider_get(
            provider="fabric",
            url="https://api.fabric.microsoft.com/v1/operations/op-1",
            access_token="token-a",
        )

    assert transport.calls == 3


@pytest.mark.asyncio
async def test_a_cached_read_is_never_replayed_to_another_token(transport):
    # Two principals can have very different access to the same URL.
    for token in ("token-a", "token-b"):
        await provider_get(
            provider="powerbi",
            url="https://api.powerbi.com/v1.0/myorg/groups",
            access_token=token,
            cacheable=True,
        )

    assert transport.calls == 2


@pytest.mark.asyncio
async def test_different_query_parameters_are_cached_separately(transport):
    for skip in (0, 100):
        await provider_get(
            provider="powerbi",
            url="https://api.powerbi.com/v1.0/myorg/groups",
            access_token="token-a",
            params={"$top": 100, "$skip": skip},
            cacheable=True,
        )

    assert transport.calls == 2


@pytest.mark.asyncio
async def test_parameter_order_does_not_split_the_cache(transport):
    await provider_get(
        provider="powerbi",
        url="https://api.powerbi.com/v1.0/myorg/groups",
        access_token="token-a",
        params={"$top": 100, "$skip": 0},
        cacheable=True,
    )
    await provider_get(
        provider="powerbi",
        url="https://api.powerbi.com/v1.0/myorg/groups",
        access_token="token-a",
        params={"$skip": 0, "$top": 100},
        cacheable=True,
    )

    assert transport.calls == 1


@pytest.mark.asyncio
async def test_concurrent_identical_reads_share_one_request(transport):
    async def slow_request(*, method, url, **kwargs):
        transport.calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=_workspaces_payload())

    transport.request = slow_request

    await asyncio.gather(
        *(
            provider_get(
                provider="powerbi",
                url="https://api.powerbi.com/v1.0/myorg/groups",
                access_token="token-a",
                cacheable=True,
            )
            for _ in range(6)
        )
    )

    assert transport.calls == 1


@pytest.mark.asyncio
async def test_a_failed_read_is_not_cached(transport):
    transport.status_code = 500

    with pytest.raises(Exception):
        await provider_get(
            provider="powerbi",
            url="https://api.powerbi.com/v1.0/myorg/groups",
            access_token="token-a",
            cacheable=True,
        )

    transport.status_code = 200
    response = await provider_get(
        provider="powerbi",
        url="https://api.powerbi.com/v1.0/myorg/groups",
        access_token="token-a",
        cacheable=True,
    )

    # A permission just granted takes effect on the next try, rather than
    # being remembered as a failure for the rest of the session.
    assert response.json() == _workspaces_payload()
    assert transport.calls == 2


@pytest.mark.asyncio
async def test_clearing_one_session_leaves_another_alone(transport):
    for token in ("token-a", "token-b"):
        await provider_get(
            provider="powerbi",
            url="https://api.powerbi.com/v1.0/myorg/groups",
            access_token=token,
            cacheable=True,
        )
    assert transport.calls == 2

    get_provider_read_cache().invalidate_session("token-a")

    await provider_get(
        provider="powerbi",
        url="https://api.powerbi.com/v1.0/myorg/groups",
        access_token="token-b",
        cacheable=True,
    )
    assert transport.calls == 2  # still cached

    await provider_get(
        provider="powerbi",
        url="https://api.powerbi.com/v1.0/myorg/groups",
        access_token="token-a",
        cacheable=True,
    )
    assert transport.calls == 3  # refetched


@pytest.mark.asyncio
async def test_repeated_client_reads_go_out_once(transport):
    client = PowerBIClient()

    for _ in range(3):
        workspaces = await client.get_workspaces(
            access_token="token-a",
            top=100,
            skip=0,
        )
        assert [item["name"] for item in workspaces] == ["POC"]

    assert transport.calls == 1


@pytest.mark.asyncio
async def test_a_disabled_cache_passes_every_read_through():
    cache = ProviderReadCache(ttl_seconds=0, max_entries=16)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return "value"

    for _ in range(3):
        assert await cache.get_or_fetch(("key",), factory) == "value"

    assert cache.enabled is False
    assert calls == 3
