import pytest

from app.ai.models.enums import MessageRole
from app.ai.models.messages import ModelMessage
from app.ai.models.requests import ModelRequest
from app.ai.providers.litellm_gateway import LiteLLMModelGateway
from app.core.exceptions import (
    AIProviderAuthenticationError,
    AIProviderError,
    AIProviderRateLimitedError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)

try:
    # litellm's own import chain can attempt a one-time network fetch for a
    # bundled tokenizer. That's orthogonal to the correctness of this
    # gateway's request/response mapping and error normalization, so these
    # tests skip cleanly (instead of failing test collection for the whole
    # suite) in a network-restricted environment rather than pretending the
    # import always succeeds.
    import litellm
    import litellm.exceptions as litellm_exceptions

    _LITELLM_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # noqa: BLE001 - deliberately broad, see comment above
    litellm = None
    litellm_exceptions = None
    _LITELLM_IMPORT_ERROR = exc

pytestmark = pytest.mark.skipif(
    _LITELLM_IMPORT_ERROR is not None,
    reason=f"litellm is not importable in this environment: {_LITELLM_IMPORT_ERROR}",
)


def _request(message: str = "Explain Gross Margin") -> ModelRequest:
    return ModelRequest(
        messages=[
            ModelMessage(
                role=MessageRole.SYSTEM,
                content="system prompt",
            ),
            ModelMessage(
                role=MessageRole.USER,
                content=message,
            ),
        ]
    )


def _litellm_gateway() -> LiteLLMModelGateway:
    return LiteLLMModelGateway(
        provider="openai",
        model="gpt-4o-mini",
        api_key="test-key",
        api_base=None,
        api_version=None,
        temperature=0.1,
        max_tokens=100,
        timeout_seconds=5.0,
    )


class _FakeUsage:
    def __init__(self) -> None:
        self.prompt_tokens = 10
        self.completion_tokens = 5
        self.total_tokens = 15


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str, finish_reason: str | None = None) -> None:
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason
        self.delta = _FakeMessage(content)


class _FakeCompletionResult:
    def __init__(self, content: str, finish_reason: str | None = "stop") -> None:
        self.choices = [_FakeChoice(content, finish_reason=finish_reason)]
        self.usage = _FakeUsage()


@pytest.mark.asyncio
async def test_litellm_gateway_generate_normalizes_successful_response(
    monkeypatch,
):
    captured_kwargs: dict = {}

    async def fake_acompletion(**kwargs):
        captured_kwargs.update(kwargs)
        return _FakeCompletionResult("Gross Margin % measures profitability.")

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    response = await _litellm_gateway().generate(_request())

    assert captured_kwargs["model"] == "openai/gpt-4o-mini"
    assert captured_kwargs["api_key"] == "test-key"
    assert response.provider == "openai"
    assert response.model == "openai/gpt-4o-mini"
    assert response.content == "Gross Margin % measures profitability."
    assert response.usage.total_tokens == 15
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_litellm_gateway_stream_normalizes_chunks(
    monkeypatch,
):
    async def fake_stream():
        yield _FakeCompletionResult("Gross ", finish_reason=None)
        yield _FakeCompletionResult("Margin", finish_reason="stop")

    async def fake_acompletion(**kwargs):
        assert kwargs["stream"] is True
        return fake_stream()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    chunks = [chunk async for chunk in _litellm_gateway().stream(_request())]

    assert [chunk.delta for chunk in chunks] == ["Gross ", "Margin"]
    assert chunks[0].finished is False
    assert chunks[1].finished is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("build_error", "expected_exception"),
    [
        (
            lambda: litellm_exceptions.AuthenticationError(
                message="invalid key",
                llm_provider="openai",
                model="gpt-4o-mini",
            ),
            AIProviderAuthenticationError,
        ),
        (
            lambda: litellm_exceptions.RateLimitError(
                message="too many requests",
                llm_provider="openai",
                model="gpt-4o-mini",
            ),
            AIProviderRateLimitedError,
        ),
        (
            lambda: litellm_exceptions.Timeout(
                message="timed out",
                llm_provider="openai",
                model="gpt-4o-mini",
            ),
            AIProviderTimeoutError,
        ),
        (
            lambda: litellm_exceptions.APIConnectionError(
                message="connection failed",
                llm_provider="openai",
                model="gpt-4o-mini",
            ),
            AIProviderUnavailableError,
        ),
        (
            lambda: litellm_exceptions.ServiceUnavailableError(
                message="unavailable",
                llm_provider="openai",
                model="gpt-4o-mini",
            ),
            AIProviderUnavailableError,
        ),
        (
            lambda: ValueError("unexpected"),
            AIProviderError,
        ),
    ],
)
async def test_litellm_gateway_maps_provider_errors(
    monkeypatch,
    build_error,
    expected_exception,
):
    async def fake_acompletion(**kwargs):
        raise build_error()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    with pytest.raises(expected_exception):
        await _litellm_gateway().generate(_request())
