from collections.abc import AsyncIterator
from typing import Any

from app.ai.models.requests import ModelRequest
from app.ai.models.responses import ModelChunk, ModelResponse, TokenUsage
from app.core.exceptions import (
    AIProviderAuthenticationError,
    AIProviderError,
    AIProviderRateLimitedError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)

_LITELLM_MODEL_PREFIX = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "azure_openai": "azure",
}


class LiteLLMModelGateway:
    """ModelGateway backed by LiteLLM's unified acompletion() API.

    Provider switching (OpenAI/Anthropic/Gemini/Azure OpenAI/...) is a
    configuration change only: the provider name selects the LiteLLM model
    prefix, credentials/endpoint come from Settings. No vendor SDK is ever
    imported or referenced outside this file.

    `litellm` is imported lazily, inside the methods below, rather than at
    module import time. LiteLLM's own import chain can attempt a one-time
    network fetch for a bundled tokenizer; deferring the import means the
    application can always start (and AI_PROVIDER=fake always works) even
    in a network-restricted environment, and a failure here becomes a
    normal, catchable per-request error instead of an app-startup crash.
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str | None,
        api_base: str | None,
        api_version: str | None,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
    ) -> None:
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._api_version = api_version
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds

    def _model_identifier(
        self,
        request: ModelRequest,
    ) -> str:
        prefix = _LITELLM_MODEL_PREFIX.get(self._provider, self._provider)
        model_name = request.model or self._model

        return f"{prefix}/{model_name}"

    def _call_kwargs(
        self,
        request: ModelRequest,
    ) -> dict[str, Any]:
        return {
            "model": self._model_identifier(request),
            "messages": [
                {
                    "role": message.role.value,
                    "content": message.content,
                }
                for message in request.messages
            ],
            "temperature": (
                request.temperature
                if request.temperature is not None
                else self._temperature
            ),
            "max_tokens": (
                request.max_tokens
                if request.max_tokens is not None
                else self._max_tokens
            ),
            "timeout": (
                request.timeout_seconds
                if request.timeout_seconds is not None
                else self._timeout_seconds
            ),
            "api_key": self._api_key,
            "base_url": self._api_base,
            "api_version": self._api_version,
        }

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        import litellm

        try:
            result = await litellm.acompletion(**self._call_kwargs(request))
        except Exception as exc:
            raise self._map_error(exc) from exc

        choice = result.choices[0]
        usage = result.usage

        return ModelResponse(
            content=choice.message.content or "",
            provider=self._provider,
            model=self._model_identifier(request),
            usage=TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            ),
            finish_reason=choice.finish_reason,
        )

    async def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelChunk]:
        import litellm

        try:
            response_stream = await litellm.acompletion(
                **self._call_kwargs(request),
                stream=True,
            )

            async for chunk in response_stream:
                choice = chunk.choices[0]
                delta = choice.delta.content or ""
                is_final = choice.finish_reason is not None

                yield ModelChunk(
                    delta=delta,
                    finished=is_final,
                )
        except Exception as exc:
            raise self._map_error(exc) from exc

    @staticmethod
    def _map_error(
        exc: Exception,
    ) -> Exception:
        import litellm.exceptions as litellm_exceptions

        if isinstance(exc, litellm_exceptions.AuthenticationError):
            return AIProviderAuthenticationError()

        if isinstance(exc, litellm_exceptions.RateLimitError):
            return AIProviderRateLimitedError()

        if isinstance(exc, litellm_exceptions.Timeout):
            return AIProviderTimeoutError()

        if isinstance(
            exc,
            (
                litellm_exceptions.APIConnectionError,
                litellm_exceptions.ServiceUnavailableError,
            ),
        ):
            return AIProviderUnavailableError()

        return AIProviderError(detail=str(exc))
