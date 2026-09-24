import httpx
import pytest

from app.clients.provider_http_client import (
    _handle_provider_response,
    close_provider_http_client,
    get_provider_http_client,
    provider_error_detail_from_payload,
)
from app.core.exceptions import (
    UpstreamRequestError,
)


def test_provider_error_detail_from_nested_payload():
    detail = provider_error_detail_from_payload(
        {
            "error": {
                "errorCode": "InvalidFormat",
                "message": ("The requested format is invalid."),
            }
        },
        status_code=400,
    )

    assert detail == ("Status 400. InvalidFormat: The requested format is invalid.")


def test_handle_provider_response_includes_provider_error_detail():
    response = httpx.Response(
        status_code=400,
        json={
            "error": {
                "errorCode": "InvalidFormat",
                "message": ("Report format TMDL is invalid."),
            }
        },
    )

    with pytest.raises(UpstreamRequestError) as exc_info:
        _handle_provider_response(
            response=response,
            provider="fabric",
        )

    assert exc_info.value.message == (
        "The request to Fabric could not be "
        "completed. Status 400. InvalidFormat: "
        "Report format TMDL is invalid."
    )


@pytest.mark.asyncio
async def test_provider_http_client_is_pooled_and_reused():
    # A fresh AsyncClient per call meant a new DNS lookup, TCP connect and TLS
    # handshake for every upstream request, including each poll of a
    # long-running operation.
    await close_provider_http_client()
    try:
        first = await get_provider_http_client()
        second = await get_provider_http_client()

        assert first is second
        assert not first.is_closed
    finally:
        await close_provider_http_client()


@pytest.mark.asyncio
async def test_provider_http_client_is_rebuilt_after_close():
    first = await get_provider_http_client()
    await close_provider_http_client()

    assert first.is_closed

    second = await get_provider_http_client()
    try:
        assert second is not first
        assert not second.is_closed
    finally:
        await close_provider_http_client()
