import pytest

from app.ai.context.resolver import AIContextResolver
from app.ai.models.requests import AIChatContext
from app.core.exceptions import (
    InsufficientPermissionsError,
    ProviderResourceNotFoundError,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelMeasure,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.report import Report
from app.schemas.workspace import Workspace
from app.services.report_service import ReportService
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.workspace_service import WorkspaceService
from tests.unit.ai_fixtures import (
    REPORT_ID,
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_semantic_model,
)


def _resolver() -> AIContextResolver:
    return AIContextResolver(
        powerbi_access_token="pbi-token",
        fabric_access_token="fabric-token",
    )


@pytest.mark.asyncio
async def test_resolve_valid_workspace_report_and_object(monkeypatch):
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

    resolved = await _resolver().resolve(
        AIChatContext(
            workspace_id=WORKSPACE_ID,
            semantic_model_id=SEMANTIC_MODEL_ID,
            object_type="measure",
            object_name="Gross Margin %",
        )
    )

    assert resolved.workspace_id == WORKSPACE_ID
    assert resolved.semantic_model_id == SEMANTIC_MODEL_ID
    assert resolved.parsed_semantic_model is not None
    assert resolved.resolved_object is not None
    assert resolved.resolved_object.object_type == "measure"
    assert resolved.resolved_object.qualified_name == "Sales[Gross Margin %]"
    assert resolved.resolution_notes == []


@pytest.mark.asyncio
async def test_resolve_rejects_inaccessible_workspace(monkeypatch):
    async def fake_get_workspace(self, *, workspace_id, access_token):
        raise ProviderResourceNotFoundError("powerbi", "workspace")

    monkeypatch.setattr(WorkspaceService, "get_workspace", fake_get_workspace)

    resolved = await _resolver().resolve(AIChatContext(workspace_id="does-not-exist"))

    assert resolved.workspace_id is None
    assert resolved.resolution_notes


@pytest.mark.asyncio
async def test_resolve_rejects_forbidden_workspace_identically_to_missing(
    monkeypatch,
):
    """A well-formed but unauthorized (cross-tenant) GUID must fail exactly
    like a nonexistent one -- no information-leaking distinction."""

    async def fake_get_workspace_forbidden(self, *, workspace_id, access_token):
        raise InsufficientPermissionsError("powerbi")

    async def fake_get_workspace_not_found(self, *, workspace_id, access_token):
        raise ProviderResourceNotFoundError("powerbi", "workspace")

    monkeypatch.setattr(WorkspaceService, "get_workspace", fake_get_workspace_forbidden)
    forbidden = await _resolver().resolve(
        AIChatContext(workspace_id="11111111-2222-3333-4444-555555555555")
    )

    monkeypatch.setattr(WorkspaceService, "get_workspace", fake_get_workspace_not_found)
    missing = await _resolver().resolve(
        AIChatContext(workspace_id="66666666-7777-8888-9999-000000000000")
    )

    assert forbidden.workspace_id is None
    assert missing.workspace_id is None
    assert forbidden.resolution_notes == missing.resolution_notes


@pytest.mark.asyncio
async def test_resolve_report_outside_workspace_is_rejected(monkeypatch):
    async def fake_get_workspace(self, *, workspace_id, access_token):
        return Workspace(id=workspace_id, name="Sales Workspace")

    async def fake_get_report_not_found(self, *, workspace_id, report_id, access_token):
        raise ProviderResourceNotFoundError("powerbi", "report")

    monkeypatch.setattr(WorkspaceService, "get_workspace", fake_get_workspace)
    monkeypatch.setattr(ReportService, "get_report", fake_get_report_not_found)

    resolved = await _resolver().resolve(
        AIChatContext(workspace_id=WORKSPACE_ID, report_id="not-in-workspace")
    )

    assert resolved.workspace_id == WORKSPACE_ID
    assert resolved.report_id is None
    assert resolved.resolution_notes


@pytest.mark.asyncio
async def test_resolve_valid_report_fetches_definition(monkeypatch):
    from app.services.report_definition_service import ReportDefinitionService
    from tests.unit.ai_fixtures import sample_report_definition

    async def fake_get_workspace(self, *, workspace_id, access_token):
        return Workspace(id=workspace_id, name="Sales Workspace")

    async def fake_get_report(self, *, workspace_id, report_id, access_token):
        return Report(id=report_id, name="Sales Report")

    async def fake_get_normalized_definition(
        self, *, workspace_id, report_id, access_token, definition_format="PBIR"
    ):
        return sample_report_definition()

    async def fake_get_parsed_definition(
        self, *, workspace_id, semantic_model_id, access_token, definition_format="TMDL"
    ):
        return sample_semantic_model()

    monkeypatch.setattr(WorkspaceService, "get_workspace", fake_get_workspace)
    monkeypatch.setattr(ReportService, "get_report", fake_get_report)
    monkeypatch.setattr(
        ReportDefinitionService,
        "get_normalized_definition",
        fake_get_normalized_definition,
    )
    monkeypatch.setattr(
        SemanticModelDefinitionService,
        "get_parsed_definition",
        fake_get_parsed_definition,
    )

    resolved = await _resolver().resolve(
        AIChatContext(workspace_id=WORKSPACE_ID, report_id=REPORT_ID)
    )

    assert resolved.report_id == REPORT_ID
    assert resolved.report_name == "Sales Report"
    assert resolved.report_definition is not None
    assert resolved.report_definition.report_id == REPORT_ID
    # No semantic_model_id was sent: the report's own binding names it, so
    # "explain this report" can still reach the measures and sources behind it.
    assert resolved.semantic_model_id == SEMANTIC_MODEL_ID
    assert resolved.parsed_semantic_model is not None


@pytest.mark.asyncio
async def test_resolve_semantic_model_not_verified(monkeypatch):
    async def fake_get_workspace(self, *, workspace_id, access_token):
        return Workspace(id=workspace_id, name="Sales Workspace")

    async def fake_get_parsed_definition_fails(
        self, *, workspace_id, semantic_model_id, access_token, definition_format="TMDL"
    ):
        raise ProviderResourceNotFoundError("fabric", "semantic model")

    monkeypatch.setattr(WorkspaceService, "get_workspace", fake_get_workspace)
    monkeypatch.setattr(
        SemanticModelDefinitionService,
        "get_parsed_definition",
        fake_get_parsed_definition_fails,
    )

    resolved = await _resolver().resolve(
        AIChatContext(workspace_id=WORKSPACE_ID, semantic_model_id="missing-model")
    )

    assert resolved.semantic_model_id is None
    assert resolved.parsed_semantic_model is None
    assert resolved.resolution_notes


@pytest.mark.asyncio
async def test_resolve_ambiguous_object_name(monkeypatch):
    duplicate_name_model = ParsedSemanticModelResponse(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="TableA",
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Revenue",
                        expression="SUM(TableA[Amount])",
                    )
                ],
            ),
            ParsedSemanticModelTable(
                name="TableB",
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Revenue",
                        expression="SUM(TableB[Amount])",
                    )
                ],
            ),
        ],
    )

    async def fake_get_workspace(self, *, workspace_id, access_token):
        return Workspace(id=workspace_id, name="Sales Workspace")

    async def fake_get_parsed_definition(
        self, *, workspace_id, semantic_model_id, access_token, definition_format="TMDL"
    ):
        return duplicate_name_model

    monkeypatch.setattr(WorkspaceService, "get_workspace", fake_get_workspace)
    monkeypatch.setattr(
        SemanticModelDefinitionService,
        "get_parsed_definition",
        fake_get_parsed_definition,
    )

    resolved = await _resolver().resolve(
        AIChatContext(
            workspace_id=WORKSPACE_ID,
            semantic_model_id=SEMANTIC_MODEL_ID,
            object_type="measure",
            object_name="Revenue",
        )
    )

    assert resolved.resolved_object is None
    assert resolved.resolution_notes


@pytest.mark.asyncio
async def test_resolve_unknown_object_name_is_unresolved(monkeypatch):
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

    resolved = await _resolver().resolve(
        AIChatContext(
            workspace_id=WORKSPACE_ID,
            semantic_model_id=SEMANTIC_MODEL_ID,
            object_type="measure",
            object_name="XYZ Revenue Forecast Measure",
        )
    )

    assert resolved.resolved_object is None
    assert resolved.resolution_notes
