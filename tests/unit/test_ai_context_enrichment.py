"""The resolver's best-effort enrichment: names, model home, related reports."""

import pytest

from app.ai.context.resolver import AIContextResolver
from app.ai.models.requests import AIChatContext
from app.core.exceptions import ProviderResourceNotFoundError
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelTable,
)
from app.schemas.report import Report, ReportListResponse
from app.schemas.semantic_model import SemanticModel, SemanticModelListResponse
from app.schemas.workspace import Workspace, WorkspaceListResponse
from app.services.report_definition_service import ReportDefinitionService
from app.services.report_service import ReportService
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.semantic_model_service import SemanticModelService
from app.services.workspace_service import WorkspaceService
from tests.unit.ai_fixtures import (
    REPORT_ID,
    SEMANTIC_MODEL_ID,
    sample_report_definition,
    sample_semantic_model,
)

REPORT_WORKSPACE = "ws-report"
MODEL_WORKSPACE = "ws-model"
WORKSPACES = {REPORT_WORKSPACE: "POC", MODEL_WORKSPACE: "DEV"}


def _resolver() -> AIContextResolver:
    return AIContextResolver(
        powerbi_access_token="pbi-token",
        fabric_access_token="fabric-token",
    )


@pytest.fixture
def tenant(monkeypatch, ai_enrichment):
    """A report in POC bound to a model that lives in DEV.

    Power BI does not report `datasetWorkspaceId` for it, which is the case
    this tenant actually has.
    """
    calls = {"definitions": []}

    async def get_workspace(self, *, workspace_id, access_token):
        return Workspace(id=workspace_id, name=WORKSPACES[workspace_id])

    async def list_workspaces(self, *, access_token, top, skip):
        workspaces = [Workspace(id=key, name=name) for key, name in WORKSPACES.items()]
        return WorkspaceListResponse(workspaces=workspaces, count=2, top=top, skip=skip)

    async def get_report(self, *, workspace_id, report_id, access_token):
        return Report(
            id=report_id, name="check_remane_app", dataset_id=SEMANTIC_MODEL_ID
        )

    async def list_reports(self, *, workspace_id, access_token):
        reports = {
            REPORT_WORKSPACE: [
                Report(
                    id=REPORT_ID, name="check_remane_app", dataset_id=SEMANTIC_MODEL_ID
                ),
                Report(id="unrelated", name="Other model", dataset_id="another-model"),
            ],
            MODEL_WORKSPACE: [
                Report(id="finance", name="Finance Pack", dataset_id=SEMANTIC_MODEL_ID),
            ],
        }[workspace_id]
        return ReportListResponse(
            workspace_id=workspace_id, reports=reports, count=len(reports)
        )

    async def list_semantic_models(self, *, workspace_id, access_token):
        models = (
            [SemanticModel(id=SEMANTIC_MODEL_ID, name="sales")]
            if workspace_id == MODEL_WORKSPACE
            else []
        )
        return SemanticModelListResponse(
            workspace_id=workspace_id, semantic_models=models, count=len(models)
        )

    async def get_parsed_definition(
        self, *, workspace_id, semantic_model_id, access_token, definition_format="TMDL"
    ):
        if workspace_id != MODEL_WORKSPACE:
            raise ProviderResourceNotFoundError("fabric", "semantic model")
        model = sample_semantic_model().model_copy(
            update={"workspace_id": workspace_id}
        )
        model.tables.append(
            ParsedSemanticModelTable(
                name="LocalDateTable_1234",
                columns=[ParsedSemanticModelColumn(name="Date")],
            )
        )
        return model

    async def get_normalized_definition(
        self, *, workspace_id, report_id, access_token, definition_format="PBIR"
    ):
        calls["definitions"].append(report_id)
        return sample_report_definition().model_copy(
            update={"workspace_id": workspace_id, "report_id": report_id}
        )

    monkeypatch.setattr(WorkspaceService, "get_workspace", get_workspace)
    monkeypatch.setattr(WorkspaceService, "list_workspaces", list_workspaces)
    monkeypatch.setattr(ReportService, "get_report", get_report)
    monkeypatch.setattr(ReportService, "list_reports", list_reports)
    monkeypatch.setattr(
        SemanticModelService, "list_semantic_models", list_semantic_models
    )
    monkeypatch.setattr(
        SemanticModelDefinitionService, "get_parsed_definition", get_parsed_definition
    )
    monkeypatch.setattr(
        ReportDefinitionService, "get_normalized_definition", get_normalized_definition
    )
    return calls


@pytest.mark.asyncio
async def test_a_report_on_a_model_in_another_workspace_still_resolves(tenant):
    resolved = await _resolver().resolve(
        AIChatContext(
            workspace_id=REPORT_WORKSPACE,
            report_id=REPORT_ID,
            semantic_model_id=SEMANTIC_MODEL_ID,
            object_type="report",
            object_id=REPORT_ID,
            object_name="check_remane_app",
        )
    )

    assert resolved.report_name == "check_remane_app"
    assert resolved.parsed_semantic_model is not None
    assert resolved.semantic_model_workspace_id == MODEL_WORKSPACE
    assert resolved.semantic_model_workspace_name == "DEV"
    assert resolved.semantic_model_name == "sales"
    # A report's name is not a model object; searching the model for it only
    # produced a note that blocked the answer.
    assert resolved.resolved_object is None
    assert resolved.resolution_notes == []
    # Auto Date/Time tables are dropped, as in every explorer dataset.
    assert all(
        not table.name.startswith("LocalDateTable_")
        for table in resolved.parsed_semantic_model.tables
    )
    # Report-scoped: the model's other reports are not fetched.
    assert resolved.related_reports == []


@pytest.mark.asyncio
async def test_an_object_question_checks_every_report_on_the_model(tenant):
    resolved = await _resolver().resolve(
        AIChatContext(
            workspace_id=REPORT_WORKSPACE,
            report_id=REPORT_ID,
            semantic_model_id=SEMANTIC_MODEL_ID,
            semantic_model_workspace_id=MODEL_WORKSPACE,
            object_type="measure",
            object_name="Sales[Gross Margin %]",
        )
    )

    assert resolved.resolved_object is not None
    assert resolved.resolved_object.qualified_name == "Sales[Gross Margin %]"
    # The report in context is not fetched twice; the unrelated one is skipped.
    assert [report.report_name for report in resolved.related_reports] == [
        "Finance Pack"
    ]
    assert resolved.related_reports[0].workspace_name == "DEV"
    assert tenant["definitions"].count(REPORT_ID) == 1
    assert "unrelated" not in tenant["definitions"]
    assert resolved.physical_sources is not None


@pytest.mark.asyncio
async def test_an_unreadable_related_report_is_named_not_fatal(tenant, monkeypatch):
    async def failing_definition(
        self, *, workspace_id, report_id, access_token, definition_format="PBIR"
    ):
        if report_id == "finance":
            raise ProviderResourceNotFoundError("fabric", "report")
        return sample_report_definition()

    monkeypatch.setattr(
        ReportDefinitionService, "get_normalized_definition", failing_definition
    )

    resolved = await _resolver().resolve(
        AIChatContext(
            workspace_id=REPORT_WORKSPACE,
            report_id=REPORT_ID,
            semantic_model_id=SEMANTIC_MODEL_ID,
            object_type="measure",
            object_name="Gross Margin %",
        )
    )

    assert resolved.resolved_object is not None
    assert resolved.related_reports == []
    assert any("Finance Pack" in note for note in resolved.coverage_notes)
    assert resolved.resolution_notes == []
