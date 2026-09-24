import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.provider_read_cache import (
    reset_provider_read_cache,
)


@pytest.fixture(autouse=True)
def _reset_provider_read_cache():
    # The read cache is process-global by design (it is shared across
    # requests), so it has to be cleared between tests or one test's cached
    # response answers the next test's call.
    reset_provider_read_cache()
    yield
    reset_provider_read_cache()


@pytest.fixture
def client():
    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client
