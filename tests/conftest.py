import pytest
from fastapi.testclient import TestClient

from app.ai.context.resolver import AIContextResolver
from app.ai.services.conversation_store import reset_conversation_store
from app.main import app
from app.services.provider_read_cache import (
    reset_provider_read_cache,
)

# The AI resolver's best-effort enrichment lists workspaces, models and
# reports with the caller's token. Tests mock the calls they care about at
# the service level; anything else would reach the real Power BI API with a
# fake token. These steps are stubbed out unless a test asks for them with
# the `ai_enrichment` fixture.
_AI_ENRICHMENT_STEPS = (
    "_enrich_names",
    "_enrich_related_reports",
    "_find_model_workspace",
)
_ORIGINAL_AI_ENRICHMENT = {
    name: getattr(AIContextResolver, name) for name in _AI_ENRICHMENT_STEPS
}


@pytest.fixture(autouse=True)
def _reset_provider_read_cache():
    # The read cache is process-global by design (it is shared across
    # requests), so it has to be cleared between tests or one test's cached
    # response answers the next test's call.
    reset_provider_read_cache()
    yield
    reset_provider_read_cache()


@pytest.fixture(autouse=True)
def _reset_conversation_store():
    # Process-global for the same reason as the read cache above.
    reset_conversation_store()
    yield
    reset_conversation_store()


@pytest.fixture(autouse=True)
def _stub_ai_enrichment(monkeypatch):
    async def skipped(*args, **kwargs):
        return None

    for name in _AI_ENRICHMENT_STEPS:
        monkeypatch.setattr(AIContextResolver, name, skipped)


@pytest.fixture
def ai_enrichment(monkeypatch):
    """Run the resolver's real enrichment steps (mock their services)."""
    for name, original in _ORIGINAL_AI_ENRICHMENT.items():
        monkeypatch.setattr(AIContextResolver, name, original)


@pytest.fixture
def client():
    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client
