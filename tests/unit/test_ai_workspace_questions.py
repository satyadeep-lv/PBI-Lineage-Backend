"""Workspace-level questions, and questions about Power AI itself.

With only a workspace selected, every question -- "What can Power AI help me
with here?", "how many reports we have in this workspace", even "hi" -- used
to end at "No semantic model or report is in context yet". These cover the
routing, the workspace evidence, and both answer paths (deterministic and
model-driven).
"""

import pytest

from app.ai.agents.workspace_agent import WorkspaceAgent
from app.ai.composition.deterministic_renderer import DeterministicAnswerRenderer
from app.ai.composition.suggested_questions import suggested_questions_for
from app.ai.context.resolver import AIContextResolver
from app.ai.models.context import (
    ResolvedAIContext,
    WorkspaceInventory,
    WorkspaceInventoryItem,
    WorkspaceInventoryReport,
    WorkspaceInventorySemanticModel,
)
from app.ai.models.enums import AIAnswerStatus, AIIntent, AudienceType
from app.ai.models.requests import AIChatContext, AIChatRequest
from app.ai.orchestration.intent import (
    capability_kind,
    classify_intent,
    wants_workspace_inventory,
)
from app.ai.orchestration.supervisor import Supervisor
from app.ai.orchestration.tool_loop import run_tool_loop
from app.ai.services.ai_service import AIService
from app.ai.tools.registry import tool_schemas
from app.clients.fabric_client import FabricClient
from app.core.config import Settings
from app.core.exceptions import InsufficientPermissionsError
from app.schemas.report import Report, ReportListResponse
from app.schemas.semantic_model import SemanticModel, SemanticModelListResponse
from app.schemas.workspace import Workspace
from app.services.report_service import ReportService
from app.services.semantic_model_service import SemanticModelService
from app.services.workspace_service import WorkspaceService
from tests.unit.ai_fixtures import (
    REPORT_ID,
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_semantic_model,
)
from tests.unit.test_tool_loop import ScriptedGateway

WORKSPACE_ONLY = AIChatContext(workspace_id=WORKSPACE_ID)
REPORT_OPEN = AIChatContext(
    workspace_id=WORKSPACE_ID,
    report_id=REPORT_ID,
    object_type="report",
)
MODEL_OPEN = AIChatContext(
    workspace_id=WORKSPACE_ID,
    semantic_model_id=SEMANTIC_MODEL_ID,
)


def _inventory() -> WorkspaceInventory:
    return WorkspaceInventory(
        reports=[
            WorkspaceInventoryReport(id="r1", name="sales", semantic_model_id="m1"),
            WorkspaceInventoryReport(
                id="r2",
                name="Invoices",
                report_type="PaginatedReport",
                semantic_model_id="m1",
            ),
            WorkspaceInventoryReport(
                id="r3",
                name="Remote",
                semantic_model_id="elsewhere",
            ),
        ],
        semantic_models=[
            WorkspaceInventorySemanticModel(id="m1", name="sales"),
            WorkspaceInventorySemanticModel(id="m2", name="Unused Model"),
        ],
        other_items=[
            WorkspaceInventoryItem(id="d1", name="KPIs", item_type="Dashboard"),
            WorkspaceInventoryItem(id="k1", name="Logs", item_type="KQLDatabase"),
        ],
    )


def _workspace_context(**overrides) -> ResolvedAIContext:
    return ResolvedAIContext(
        workspace_id=WORKSPACE_ID,
        workspace_name="POC",
        workspace_inventory=overrides.pop("inventory", _inventory()),
        **overrides,
    )


# -- Routing ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("What can Power AI help me with here?", "help"),
        ("what can you do?", "help"),
        ("How do I use this?", "help"),
        ("What questions can I ask?", "help"),
        ("help", "help"),
        ("hi", "greeting"),
        ("Hello!", "greeting"),
        ("good morning", "greeting"),
        ("thanks!", "thanks"),
        ("Thank you", "thanks"),
    ],
)
def test_questions_about_power_ai_are_recognised(message, kind):
    assert capability_kind(message) == kind
    assert classify_intent(message, WORKSPACE_ONLY) == AIIntent.CAPABILITIES


@pytest.mark.parametrize(
    "message",
    [
        "what can you tell me about Net Sales",
        "help me with the DAX for Net Sales",
        "hi, explain Net Sales",
        "what are measures",
    ],
)
def test_real_questions_are_not_mistaken_for_help(message):
    assert capability_kind(message) is None


@pytest.mark.parametrize(
    ("message", "context"),
    [
        ("how many reports we have in this workspace", WORKSPACE_ONLY),
        # Naming the workspace wins even while a report is open.
        ("how many reports we have in this workspace", REPORT_OPEN),
        ("what's in this workspace?", MODEL_OPEN),
        ("how many reports do we have", WORKSPACE_ONLY),
        ("which semantic model does each report use", WORKSPACE_ONLY),
        ("give me an overview", WORKSPACE_ONLY),
    ],
)
def test_workspace_questions_route_to_the_workspace_agent(message, context):
    assert classify_intent(message, context) == AIIntent.WORKSPACE_INFORMATION


def test_model_questions_in_a_workspace_view_still_need_a_model():
    # "What measures are there" is about a model; the model agent says what
    # the workspace holds and to open one (see the fallback test below).
    assert (
        classify_intent("what measures are there", WORKSPACE_ONLY)
        == AIIntent.SEMANTIC_MODEL_INFORMATION
    )


@pytest.mark.parametrize(
    "message",
    ["What's in this semantic model?", "Where does its data come from?"],
)
def test_model_view_questions_route_to_the_model_agent(message):
    assert classify_intent(message, MODEL_OPEN) == AIIntent.SEMANTIC_MODEL_INFORMATION


@pytest.mark.parametrize(
    "context",
    [
        None,
        WORKSPACE_ONLY,
        REPORT_OPEN,
        MODEL_OPEN,
        AIChatContext(workspace_id=WORKSPACE_ID, report_id=REPORT_ID),
        AIChatContext(
            workspace_id=WORKSPACE_ID,
            semantic_model_id=SEMANTIC_MODEL_ID,
            object_type="measure",
            object_name="Net Sales",
        ),
    ],
)
def test_every_suggestion_routes_to_an_agent_that_can_answer(context):
    suggestions = suggested_questions_for(context)

    assert suggestions
    for question in suggestions:
        assert classify_intent(question, context) != AIIntent.OUT_OF_SCOPE, question


def test_the_inventory_is_only_listed_when_a_question_needs_it():
    assert wants_workspace_inventory("anything at all", WORKSPACE_ONLY)
    assert wants_workspace_inventory("how many reports in this workspace", REPORT_OPEN)
    assert wants_workspace_inventory("how many reports do we have", MODEL_OPEN)
    assert not wants_workspace_inventory("explain this report", REPORT_OPEN)
    assert not wants_workspace_inventory("explain Net Sales", MODEL_OPEN)
    assert not wants_workspace_inventory("how many reports", None)


# -- Evidence -----------------------------------------------------------------


def test_workspace_agent_answers_counts_names_and_bindings():
    bundle = WorkspaceAgent().gather_evidence(
        "how many reports we have in this workspace",
        _workspace_context(),
    )

    assert bundle.status == AIAnswerStatus.ANSWERED
    answer = DeterministicAnswerRenderer.render(bundle, AudienceType.GENERAL)

    assert (
        "Workspace 'POC' has 3 reports (1 paginated), 2 semantic models, "
        "1 dashboard and 1 KQL database." in answer
    )
    assert "'Invoices' (paginated report) uses semantic model 'sales'" in answer
    assert "'Remote' uses a semantic model from another workspace" in answer
    assert "'sales' is used by 2 reports in this workspace: Invoices, sales" in answer
    assert "'Unused Model' is not used by any report in this workspace" in answer
    assert "1 KQL database: Logs" in answer


def test_workspace_agent_refuses_only_when_nothing_could_be_listed():
    inventory = WorkspaceInventory(
        notes=["The workspace's reports could not be listed."]
    )

    bundle = WorkspaceAgent().gather_evidence(
        "how many reports",
        _workspace_context(inventory=inventory),
    )

    assert bundle.status == AIAnswerStatus.INSUFFICIENT_EVIDENCE
    assert bundle.missing_information == [
        "The workspace's reports could not be listed."
    ]


def test_a_model_question_with_only_a_workspace_open_says_what_it_holds():
    bundle = Supervisor().handle(
        question="what is Net Sales",
        chat_context=WORKSPACE_ONLY,
        resolved_context=_workspace_context(),
    )

    assert bundle.status == AIAnswerStatus.ANSWERED
    assert any(
        "Open a report or semantic model" in note for note in bundle.missing_information
    )
    answer = DeterministicAnswerRenderer.render(bundle, AudienceType.GENERAL)
    assert "Semantic models in this workspace" in answer


# -- Resolver -----------------------------------------------------------------


def _patch_listings(monkeypatch, *, fail_reports=False, calls=None):
    calls = calls if calls is not None else []

    async def get_workspace(self, *, workspace_id, access_token):
        return Workspace(id=workspace_id, name="POC")

    async def list_reports(self, *, workspace_id, access_token):
        calls.append("reports")
        if fail_reports:
            raise InsufficientPermissionsError("powerbi")
        return ReportListResponse(
            workspace_id=workspace_id,
            reports=[Report(id="r1", name="sales", dataset_id="m1")],
            count=1,
        )

    async def list_semantic_models(self, *, workspace_id, access_token):
        calls.append("models")
        return SemanticModelListResponse(
            workspace_id=workspace_id,
            semantic_models=[SemanticModel(id="m1", name="sales")],
            count=1,
        )

    async def list_items(self, *, workspace_id, access_token, continuation_token=None):
        calls.append("items")
        return {
            "value": [
                {"id": "r1", "displayName": "sales", "type": "Report"},
                {"id": "m1", "displayName": "sales", "type": "SemanticModel"},
                {"id": "d1", "displayName": "KPIs", "type": "Dashboard"},
            ]
        }

    monkeypatch.setattr(WorkspaceService, "get_workspace", get_workspace)
    monkeypatch.setattr(ReportService, "list_reports", list_reports)
    monkeypatch.setattr(
        SemanticModelService, "list_semantic_models", list_semantic_models
    )
    monkeypatch.setattr(FabricClient, "list_items", list_items)
    return calls


@pytest.mark.asyncio
async def test_resolver_lists_the_workspace_only_when_asked(monkeypatch):
    calls = _patch_listings(monkeypatch)
    resolver = AIContextResolver(
        powerbi_access_token="pbi",
        fabric_access_token="fabric",
    )

    without = await resolver.resolve(WORKSPACE_ONLY)
    assert without.workspace_inventory is None
    assert calls == []

    resolved = await resolver.resolve(WORKSPACE_ONLY, include_workspace_inventory=True)

    inventory = resolved.workspace_inventory
    assert [report.name for report in inventory.reports] == ["sales"]
    assert inventory.reports[0].semantic_model_id == "m1"
    assert [model.name for model in inventory.semantic_models] == ["sales"]
    # Reports and models come from Power BI; Fabric adds only the rest.
    assert [item.item_type for item in inventory.other_items] == ["Dashboard"]
    assert inventory.notes == []


@pytest.mark.asyncio
async def test_resolver_inventory_degrades_per_listing(monkeypatch):
    _patch_listings(monkeypatch, fail_reports=True)
    resolver = AIContextResolver(powerbi_access_token="pbi", fabric_access_token=None)

    resolved = await resolver.resolve(WORKSPACE_ONLY, include_workspace_inventory=True)

    inventory = resolved.workspace_inventory
    assert inventory.reports is None
    assert [model.name for model in inventory.semantic_models] == ["sales"]
    assert inventory.other_items is None
    assert len(inventory.notes) == 2


# -- Answer paths -------------------------------------------------------------


def _service(gateway=None, *, ai_enabled=True) -> AIService:
    return AIService(
        settings=Settings(ai_enabled=ai_enabled, ai_provider="fake"),
        gateway=gateway,
        powerbi_access_token="pbi",
        fabric_access_token="fabric",
    )


@pytest.mark.asyncio
async def test_the_screenshot_questions_are_answered(monkeypatch):
    _patch_listings(monkeypatch)
    service = _service()

    help_answer = await service.generate(
        AIChatRequest(
            message="What can Power AI help me with here?",
            context=WORKSPACE_ONLY,
        )
    )
    count_answer = await service.generate(
        AIChatRequest(
            message="how many reports we have in this workspace",
            context=WORKSPACE_ONLY,
        )
    )

    assert help_answer.status == AIAnswerStatus.ANSWERED
    assert help_answer.agent == "capabilities"
    assert "Workspace 'POC' has 1 report" in help_answer.answer
    assert "Try asking" in help_answer.answer
    assert help_answer.evidence[0].object_type == "workspace"
    assert help_answer.suggested_questions

    assert count_answer.status == AIAnswerStatus.ANSWERED
    assert count_answer.agent == "workspace_agent"
    assert "Workspace 'POC' has 1 report, 1 semantic model and 1 dashboard." in (
        count_answer.answer
    )
    assert count_answer.suggested_questions


@pytest.mark.asyncio
async def test_thanks_is_answered_without_resolving_anything(monkeypatch):
    service = _service()

    async def must_not_resolve(request):
        raise AssertionError("'thanks' needs no context")

    monkeypatch.setattr(service, "_resolved_context", must_not_resolve)

    response = await service.generate(
        AIChatRequest(message="thanks!", context=WORKSPACE_ONLY)
    )

    assert response.status == AIAnswerStatus.ANSWERED
    assert response.answer.startswith("You're welcome.")


@pytest.mark.asyncio
async def test_explain_answers_help_with_ai_disabled(monkeypatch):
    _patch_listings(monkeypatch)

    response = await _service(ai_enabled=False).explain(
        AIChatRequest(message="hi", context=WORKSPACE_ONLY)
    )

    assert response.status == AIAnswerStatus.ANSWERED
    assert response.answer.startswith("Hi! I'm Power AI.")


@pytest.mark.asyncio
async def test_the_model_can_answer_workspace_questions_with_the_workspace_tool(
    monkeypatch,
):
    _patch_listings(monkeypatch)
    gateway = ScriptedGateway(
        [
            {"tools": [("workspace_overview", {})]},
            {"content": "POC has 1 report, sales, built on the sales model."},
        ]
    )

    response = await _service(gateway).generate(
        AIChatRequest(message="how many reports do we have?", context=WORKSPACE_ONLY)
    )

    assert response.agent == "tool_loop"
    assert [call.tool for call in response.tool_trace] == ["workspace_overview"]
    assert response.answer.startswith("POC has 1 report")
    # With only a workspace open, that is the one tool the model is offered.
    offered = [tool["name"] for tool in gateway.requests[0].tools]
    assert offered == ["workspace_overview"]


@pytest.mark.asyncio
async def test_a_workspace_is_resolved_once_per_request(monkeypatch):
    calls = _patch_listings(monkeypatch)

    # The fake gateway gives no tool evidence, so the fixed path runs too;
    # both must share one resolution.
    await _service().generate(
        AIChatRequest(message="how many reports do we have?", context=WORKSPACE_ONLY)
    )

    assert calls.count("reports") == 1


@pytest.mark.asyncio
async def test_workspace_tool_needs_a_listed_workspace():
    assert tool_schemas(ResolvedAIContext(workspace_id=WORKSPACE_ID)) == []
    assert [schema["name"] for schema in tool_schemas(_workspace_context())] == [
        "workspace_overview"
    ]

    with_model = _workspace_context(
        semantic_model_id=SEMANTIC_MODEL_ID,
        parsed_semantic_model=sample_semantic_model(),
    )
    result = await run_tool_loop(
        ScriptedGateway([{"tools": [("workspace_overview", {})]}, {"content": "done"}]),
        question="how many reports in this workspace",
        context=with_model,
    )
    assert result.evidence[0].object_type == "workspace"


# -- Focus: what the panel's context chip shows ------------------------------


@pytest.mark.asyncio
async def test_answers_carry_the_context_the_backend_verified(monkeypatch):
    _patch_listings(monkeypatch)

    response = await _service().generate(
        AIChatRequest(message="how many reports?", context=WORKSPACE_ONLY)
    )

    assert response.focus is not None
    assert response.focus.source == "page"
    assert response.focus.workspace_name == "POC"
    assert response.focus.report_id is None


def test_focus_names_the_selected_object_and_is_empty_without_context():
    from app.ai.models.context import ResolvedObject
    from app.ai.services.ai_service import focus_of

    assert focus_of(ResolvedAIContext()) is None

    focus = focus_of(
        _workspace_context(
            semantic_model_id=SEMANTIC_MODEL_ID,
            semantic_model_name="sales",
            resolved_object=ResolvedObject(
                object_type="measure",
                table_name="Sales",
                object_name="Net Sales",
                qualified_name="Sales[Net Sales]",
            ),
        )
    )
    assert focus.semantic_model_name == "sales"
    assert (focus.object_type, focus.object_name) == ("measure", "Sales[Net Sales]")


def test_the_panel_stream_answers_a_workspace_only_question(client, monkeypatch):
    import json

    from app.api.dependencies.credentials import (
        get_optional_fabric_access_token,
        get_powerbi_access_token,
    )
    from app.main import app

    _patch_listings(monkeypatch)
    monkeypatch.setattr(
        "app.api.v1.ai.get_settings",
        lambda: Settings(ai_enabled=True, ai_provider="fake"),
    )
    app.dependency_overrides[get_powerbi_access_token] = lambda: "pbi"
    app.dependency_overrides[get_optional_fabric_access_token] = lambda: "fabric"
    try:
        # Exactly what the panel sends with only "Workspace: POC" selected.
        response = client.post(
            "/api/v1/ai/chat/stream",
            json={
                "message": "how many reports we have in this workspace",
                "audience": "developer",
                "context": {
                    "workspace_id": WORKSPACE_ID,
                    "route": "/workspace/explorer",
                },
            },
        )
    finally:
        app.dependency_overrides.pop(get_powerbi_access_token, None)
        app.dependency_overrides.pop(get_optional_fabric_access_token, None)

    events = [
        (
            block.split("\n")[0].removeprefix("event: "),
            json.loads(block.split("\n")[1].removeprefix("data: ")),
        )
        for block in response.text.strip().split("\n\n")
    ]
    metadata, complete = events[0][1], events[-1][1]

    assert metadata["status"] == "answered"
    assert metadata["focus"]["workspace_name"] == "POC"
    assert complete["status"] == "answered"
    assert "Workspace 'POC' has 1 report" in complete["answer"]
    assert complete["suggested_questions"]
