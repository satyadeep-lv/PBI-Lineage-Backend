import json

from app.api.dependencies.credentials import (
    get_optional_fabric_access_token,
    get_powerbi_access_token,
)
from app.core.config import Settings
from app.main import app
from app.schemas.workspace import Workspace
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.workspace_service import WorkspaceService
from tests.unit.ai_fixtures import (
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_semantic_model,
)


def _override_powerbi_token() -> None:
    async def fake_token() -> str:
        return "fake-test-token"

    app.dependency_overrides[get_powerbi_access_token] = fake_token


def _override_fabric_token() -> None:
    async def fake_token() -> str:
        return "fake-fabric-token"

    app.dependency_overrides[get_optional_fabric_access_token] = fake_token


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_powerbi_access_token, None)
    app.dependency_overrides.pop(get_optional_fabric_access_token, None)


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        events.append((event_name, json.loads(data) if data else {}))
    return events


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


def test_ai_chat_without_context_is_insufficient_evidence(client, monkeypatch):
    """No object/report/workspace context -> nothing to resolve -> the
    model is never asked to guess."""
    _override_powerbi_token()

    try:
        monkeypatch.setattr(
            "app.api.v1.ai.get_settings",
            lambda: Settings(ai_enabled=True, ai_provider="fake"),
        )

        response = client.post(
            "/api/v1/ai/chat",
            json={"conversation_id": "conv-1", "message": "Explain Gross Margin"},
        )

        assert response.status_code == 200

        payload = response.json()

        assert payload["conversation_id"] == "conv-1"
        assert payload["status"] == "insufficient_evidence"
        assert payload["claims"] == []
        assert payload["evidence"] == []
        assert payload["usage"] is None
        assert (
            "I could not determine this from the currently available "
            "lineage evidence" in payload["answer"]
        )
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


def test_ai_chat_answers_measure_question_end_to_end(client, monkeypatch):
    """Full path: authenticated route -> resolver (mocked provider calls
    only) -> measure agent -> real graph/DAX evidence -> grounded response,
    with the fake provider (which returns plain text, not JSON) forcing the
    deterministic fallback -- proving the exact DAX still reaches the
    caller even when model composition can't be used."""
    _override_powerbi_token()
    _override_fabric_token()

    async def fake_get_workspace(self, *, workspace_id, access_token):
        return Workspace(id=workspace_id, name="Sales Workspace")

    async def fake_get_parsed_definition(
        self, *, workspace_id, semantic_model_id, access_token, definition_format="TMDL"
    ):
        return sample_semantic_model()

    monkeypatch.setattr(WorkspaceService, "get_workspace", fake_get_workspace)
    monkeypatch.setattr(
        SemanticModelDefinitionService,
        "get_parsed_definition",
        fake_get_parsed_definition,
    )

    try:
        monkeypatch.setattr(
            "app.api.v1.ai.get_settings",
            lambda: Settings(ai_enabled=True, ai_provider="fake"),
        )

        response = client.post(
            "/api/v1/ai/chat",
            json={
                "message": "Explain Gross Margin %",
                "audience": "developer",
                "context": {
                    "workspace_id": WORKSPACE_ID,
                    "semantic_model_id": SEMANTIC_MODEL_ID,
                    "object_type": "measure",
                    "object_name": "Gross Margin %",
                },
            },
        )

        assert response.status_code == 200

        payload = response.json()

        assert payload["status"] == "answered"
        assert payload["agent"] == "measure_agent"
        assert "DIVIDE([Gross Profit], [Net Sales])" in payload["answer"]
        assert any(item["fact_type"] == "definition" for item in payload["evidence"])
    finally:
        _clear_overrides()


def test_ai_chat_stream_matches_the_frontend_event_contract(
    client,
    monkeypatch,
):
    """The frontend reads `delta.text`, and treats `complete` as the full,
    authoritative response whose `answer` replaces the streamed text.
    `complete` used to omit `answer`, so every streamed reply rendered as an
    empty bubble."""
    _override_powerbi_token()
    _override_fabric_token()

    try:
        monkeypatch.setattr(
            "app.api.v1.ai.get_settings",
            lambda: Settings(ai_enabled=True, ai_provider="fake"),
        )

        response = client.post(
            "/api/v1/ai/chat/stream",
            json={"message": "What's the weather today?"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse_events(response.text)
        event_names = [name for name, _ in events]

        assert event_names[0] == "metadata"
        assert event_names[1] == "evidence"
        assert event_names[-1] == "complete"
        assert "delta" in event_names

        complete_payload = events[-1][1]
        assert complete_payload["status"] == "out_of_scope"
        assert complete_payload["answer"]
        assert "evidence" in complete_payload
        assert complete_payload["conversation_id"] == events[0][1]["conversation_id"]

        # Deltas carry the text under the key the frontend reads, and join
        # back to exactly the final answer -- spaces and newlines intact.
        deltas = [data for name, data in events if name == "delta"]
        assert all(data["text"] == data["delta"] for data in deltas)
        assert "".join(data["text"] for data in deltas) == complete_payload["answer"]
    finally:
        _clear_overrides()


def test_ai_chat_stream_error_carries_the_reason_the_frontend_reads(
    client,
    monkeypatch,
):
    _override_powerbi_token()

    try:
        monkeypatch.setattr(
            "app.api.v1.ai.get_settings",
            lambda: Settings(ai_enabled=False),
        )

        response = client.post(
            "/api/v1/ai/chat/stream",
            json={"message": "Explain Gross Margin"},
        )

        events = _parse_sse_events(response.text)

        assert [name for name, _ in events] == ["error"]
        payload = events[0][1]
        assert payload["code"] == "AI_DISABLED"
        assert payload["reason"] == "disabled"
        assert payload["error"] == payload["message"]
    finally:
        _clear_overrides()
