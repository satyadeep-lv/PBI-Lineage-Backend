import pytest

from app.ai.models.enums import MessageRole
from app.ai.models.messages import ModelMessage
from app.ai.models.requests import ModelRequest
from app.ai.providers.fake_gateway import FakeModelGateway


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


@pytest.mark.asyncio
async def test_fake_gateway_generate_is_deterministic():
    gateway = FakeModelGateway(model="fake-model")

    response = await gateway.generate(_request("Explain Gross Margin"))

    assert response.provider == "fake"
    assert response.model == "fake-model"
    assert "Explain Gross Margin" in response.content
    assert response.usage.total_tokens > 0
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_fake_gateway_stream_reconstructs_generate_content():
    gateway = FakeModelGateway(model="fake-model")
    request = _request("Explain Gross Margin")

    full_response = await gateway.generate(request)
    chunks = [chunk async for chunk in gateway.stream(request)]

    assert "".join(chunk.delta for chunk in chunks) == full_response.content
    assert all(not chunk.finished for chunk in chunks[:-1])
    assert chunks[-1].finished is True
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.total_tokens == full_response.usage.total_tokens
