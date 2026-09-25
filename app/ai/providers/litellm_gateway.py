import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from app.ai.models.messages import ModelMessage, ModelToolCall
from app.ai.models.requests import ModelRequest
from app.ai.models.responses import ModelChunk, ModelResponse, TokenUsage
from app.core.exceptions import (
    AIProviderAuthenticationError,
    AIProviderError,
    AIProviderRateLimitedError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AppException,
)

_LITELLM_MODEL_PREFIX = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "azure_openai": "azure",
}


_IMPORT_FAILURE_TTL_SECONDS = 60.0
_litellm_module: Any = None
_litellm_import_failed_at: float | None = None
_litellm_import_error: str = ""


def _load_litellm() -> Any:
    """Import litellm once, and remember a failure for a short while.

    Python does not cache failed imports, so on a host that cannot reach
    litellm's bundled-tokenizer/model-cost-map endpoints every single request
    re-ran the whole import and waited out its retry/backoff -- measured at
    ~28 seconds per request, which reads as a hung chat box rather than a
    provider that is simply unreachable. Remembering the failure briefly
    makes the request fail fast and fall back to the deterministic answer,
    while still retrying periodically in case the network comes back.
    """
    global _litellm_module, _litellm_import_failed_at, _litellm_import_error

    if _litellm_module is not None:
        return _litellm_module

    if (
        _litellm_import_failed_at is not None
        and time.monotonic() - _litellm_import_failed_at < _IMPORT_FAILURE_TTL_SECONDS
    ):
        raise AIProviderUnavailableError(
            f"The AI client library could not be loaded: {_litellm_import_error}"
        )

    # Use the model-cost map bundled with the package instead of fetching it
    # from GitHub on import, which added ~9s to the first request.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    try:
        import litellm
    except BaseException as exc:
        _litellm_import_failed_at = time.monotonic()
        _litellm_import_error = f"{type(exc).__name__}: {exc}"[:200]
        raise AIProviderUnavailableError(
            f"The AI client library could not be loaded: {_litellm_import_error}"
        ) from exc

    _litellm_module = litellm
    _litellm_import_failed_at = None
    return litellm


def reset_litellm_import_state() -> None:
    global _litellm_module, _litellm_import_failed_at, _litellm_import_error

    _litellm_module = None
    _litellm_import_failed_at = None
    _litellm_import_error = ""


def _as_provider_message(message: ModelMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": message.role.value,
        "content": message.content,
    }

    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
            for call in message.tool_calls
        ]

    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id

    if message.name:
        payload["name"] = message.name

    return payload


def _as_tool_calls(raw: Any) -> list[ModelToolCall]:
    calls: list[ModelToolCall] = []

    for item in raw or []:
        function = getattr(item, "function", None) or {}
        name = getattr(function, "name", None) or (
            function.get("name") if isinstance(function, dict) else None
        )
        if not name:
            continue

        raw_arguments = getattr(function, "arguments", None) or (
            function.get("arguments") if isinstance(function, dict) else None
        )
        try:
            arguments = json.loads(raw_arguments) if raw_arguments else {}
        except (TypeError, ValueError):
            # A malformed argument blob must not abort the loop; the tool
            # simply runs with its defaults.
            arguments = {}

        calls.append(
            ModelToolCall(
                id=str(getattr(item, "id", None) or name),
                name=str(name),
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )

    return calls


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
        kwargs: dict[str, Any] = {
            "model": self._model_identifier(request),
            "messages": [_as_provider_message(message) for message in request.messages],
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

        if request.tools:
            kwargs["tools"] = [
                {"type": "function", "function": tool} for tool in request.tools
            ]
            # Nudging a tool on the first round keeps the model from answering
            # a lineage question from memory instead of from evidence.
            kwargs["tool_choice"] = "required" if request.require_tool else "auto"

        return kwargs

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        litellm = _load_litellm()

        try:
            result = await litellm.acompletion(**self._call_kwargs(request))
        except Exception as exc:
            raise self._map_error(exc) from exc

        choice = result.choices[0]
        usage = result.usage

        return ModelResponse(
            content=choice.message.content or "",
            tool_calls=_as_tool_calls(getattr(choice.message, "tool_calls", None)),
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
        litellm = _load_litellm()

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
        if isinstance(exc, AppException):
            return exc

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
