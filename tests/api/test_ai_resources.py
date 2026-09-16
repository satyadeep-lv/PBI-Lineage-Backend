from app.api.dependencies.credentials import get_powerbi_access_token
from app.core.config import Settings
from app.main import app


def _override_powerbi_token() -> None:
    async def fake_token() -> str:
        return "fake-test-token"

    app.dependency_overrides[get_powerbi_access_token] = fake_token


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_powerbi_access_token, None)


def test_ai_status_requires_authentication(client):
    _clear_overrides()

    response = client.get("/api/v1/ai/status")

    assert response.status_code == 401


def test_ai_status_returns_safe_configuration(client, monkeypatch):
    _override_powerbi_token()

    try:
        monkeypatch.setattr(
            "app.api.v1.ai.get_settings",
            lambda: Settings(
                ai_enabled=True,
                ai_provider="fake",
                ai_model="fake-model",
                ai_streaming_enabled=True,
            ),
        )

        response = client.get("/api/v1/ai/status")

        assert response.status_code == 200

        payload = response.json()

        assert payload == {
            "enabled": True,
            "provider": "fake",
            "model": "fake-model",
            "streaming_enabled": True,
            "configured": True,
        }
    finally:
        _clear_overrides()


def test_ai_chat_requires_authentication(client):
    _clear_overrides()

    response = client.post(
        "/api/v1/ai/chat",
        json={"message": "Explain Gross Margin"},
    )

    assert response.status_code == 401


def test_ai_chat_rejects_when_ai_disabled(client, monkeypatch):
    _override_powerbi_token()

    try:
        monkeypatch.setattr(
            "app.api.v1.ai.get_settings",
            lambda: Settings(ai_enabled=False),
        )

        response = client.post(
            "/api/v1/ai/chat",
            json={"message": "Explain Gross Margin"},
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_DISABLED"
    finally:
        _clear_overrides()


def test_ai_chat_returns_forward_compatible_response(client, monkeypatch):
    _override_powerbi_token()

    try:
        monkeypatch.setattr(
            "app.api.v1.ai.get_settings",
            lambda: Settings(
                ai_enabled=True,
                ai_provider="fake",
                ai_model="fake-model",
            ),
        )

        response = client.post(
            "/api/v1/ai/chat",
            json={
                "conversation_id": "conv-1",
                "message": "Explain Gross Margin",
                "audience": "business",
            },
        )

        assert response.status_code == 200

        payload = response.json()

        assert payload["conversation_id"] == "conv-1"
        assert payload["agent"] is None
        assert payload["evidence"] == []
        assert payload["suggested_questions"] == []
        assert "Explain Gross Margin" in payload["answer"]
        assert payload["usage"]["provider"] == "fake"
        assert payload["usage"]["tokens"] > 0
    finally:
        _clear_overrides()


def test_ai_chat_rejects_empty_message(client, monkeypatch):
    _override_powerbi_token()

    try:
        monkeypatch.setattr(
            "app.api.v1.ai.get_settings",
            lambda: Settings(ai_enabled=True, ai_provider="fake"),
        )

        response = client.post(
            "/api/v1/ai/chat",
            json={"message": ""},
        )

        assert response.status_code == 422
    finally:
        _clear_overrides()
