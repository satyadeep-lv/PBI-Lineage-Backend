import pytest

import app.clients.fabric_client as fabric_client_module
from app.clients.fabric_client import FabricClient


@pytest.mark.asyncio
async def test_start_report_definition_uses_pbir_default(
    monkeypatch,
):
    captured_call = {}

    async def fake_provider_post(**kwargs):
        captured_call.update(kwargs)

        return "fabric-response"

    monkeypatch.setattr(
        fabric_client_module,
        "provider_post",
        fake_provider_post,
    )

    result = await FabricClient().start_report_definition(
        workspace_id="workspace-123",
        report_id="report-123",
        access_token="token",
    )

    assert result == "fabric-response"
    assert captured_call == {
        "provider": "fabric",
        "url": (
            "https://api.fabric.microsoft.com/v1/"
            "workspaces/workspace-123/"
            "reports/report-123/"
            "getDefinition"
        ),
        "access_token": "token",
        "params": {"format": "PBIR"},
        "not_found_resource": "report",
    }


@pytest.mark.asyncio
async def test_start_semantic_model_definition_calls_fabric_get_definition(
    monkeypatch,
):
    captured_call = {}

    async def fake_provider_post(**kwargs):
        captured_call.update(kwargs)

        return "fabric-response"

    monkeypatch.setattr(
        fabric_client_module,
        "provider_post",
        fake_provider_post,
    )

    result = await FabricClient().start_semantic_model_definition(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        access_token="token",
        definition_format="TMSL",
    )

    assert result == "fabric-response"
    assert captured_call == {
        "provider": "fabric",
        "url": (
            "https://api.fabric.microsoft.com/v1/"
            "workspaces/workspace-123/"
            "semanticModels/model-123/"
            "getDefinition"
        ),
        "access_token": "token",
        "params": {"format": "TMSL"},
        "not_found_resource": ("semantic_model"),
    }
