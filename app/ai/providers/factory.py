from app.ai.providers.base import ModelGateway
from app.ai.providers.fake_gateway import FakeModelGateway
from app.ai.providers.litellm_gateway import LiteLLMModelGateway
from app.core.config import Settings

_CREDENTIAL_SETTINGS_BY_PROVIDER = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
    "azure_openai": "azure_openai_api_key",
}


def _resolve_api_key(settings: Settings) -> str | None:
    field_name = _CREDENTIAL_SETTINGS_BY_PROVIDER.get(settings.ai_provider)

    if field_name is None:
        return None

    credential = getattr(settings, field_name)

    return credential.get_secret_value() if credential is not None else None


def is_provider_configured(settings: Settings) -> bool:
    """Whether a credential is present for the currently selected provider.

    Used by /ai/status to report readiness without ever exposing the
    credential itself. The fake provider needs no credential.
    """
    if settings.ai_provider == "fake":
        return True

    return _resolve_api_key(settings) is not None


def build_model_gateway(settings: Settings) -> ModelGateway:
    if settings.ai_provider == "fake":
        return FakeModelGateway(model=settings.ai_model)

    return LiteLLMModelGateway(
        provider=settings.ai_provider,
        model=settings.ai_model,
        api_key=_resolve_api_key(settings),
        api_base=settings.ai_api_base,
        api_version=settings.ai_api_version,
        temperature=settings.ai_temperature,
        max_tokens=settings.ai_max_tokens,
        timeout_seconds=settings.ai_request_timeout_seconds,
    )
