"""Power AI as a conversation: what it is told, what it remembers."""

import pytest

from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import AIAnswerStatus, AudienceType, MessageRole
from app.ai.models.messages import ModelToolCall
from app.ai.models.requests import AIChatRequest
from app.ai.models.responses import ModelResponse, TokenUsage
from app.ai.services.ai_service import AIService
from app.ai.services.conversation_store import conversation_history
from app.ai.tools.lineage_tools import build_context_graph
from app.core.config import Settings
from tests.unit.ai_fixtures import (
    GROSS_MARGIN_DAX,
    REPORT_ID,
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_report_definition,
    sample_semantic_model,
)


class ScriptedGateway:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        step = self.script.pop(0) if self.script else {"content": "done"}
        return ModelResponse(
            content=step.get("content", ""),
            provider="scripted",
            model="scripted-model",
            usage=TokenUsage(total_tokens=3),
            tool_calls=[
                ModelToolCall(id=f"call-{index}", name=name, arguments=arguments)
                for index, (name, arguments) in enumerate(step.get("tools", []))
            ],
        )

    def stream(self, request):  # pragma: no cover - not used
        raise NotImplementedError


def _context(**overrides) -> ResolvedAIContext:
    defaults = dict(
        workspace_id=WORKSPACE_ID,
        workspace_name="POC",
        report_id=REPORT_ID,
        report_name="check_remane_app",
        semantic_model_id=SEMANTIC_MODEL_ID,
        semantic_model_name="sales",
        semantic_model_workspace_id=WORKSPACE_ID,
        semantic_model_workspace_name="POC",
        parsed_semantic_model=sample_semantic_model(),
        report_definition=sample_report_definition(),
    )
    defaults.update(overrides)
    return ResolvedAIContext(**defaults)


def _service(gateway, monkeypatch, context=None) -> AIService:
    service = AIService(
        settings=Settings(ai_enabled=True, ai_provider="fake"),
        gateway=gateway,
        powerbi_access_token="pbi-token",
        fabric_access_token="fabric-token",
    )

    async def fake_context(request):
        return context or _context()

    monkeypatch.setattr(service, "_resolved_context", fake_context)
    return service


@pytest.mark.asyncio
async def test_the_model_is_told_what_the_user_has_open(monkeypatch):
    # "Explain this report" only means something if the model knows which
    # report is open; it used to see the question and nothing else.
    gateway = ScriptedGateway(
        [
            {"tools": [("report_overview", {})]},
            {"content": "check_remane_app shows Gross Margin %."},
        ]
    )

    await _service(gateway, monkeypatch).generate(
        AIChatRequest(message="Explain this report")
    )

    system = gateway.requests[0].messages[0]
    assert system.role == MessageRole.SYSTEM
    assert "Report open: 'check_remane_app'" in system.content
    assert "Semantic model: 'sales'" in system.content
    assert "Visual impact" in system.content  # the answer style travels too

    # The tool result the model writes from is sectioned, readable text.
    tool_turn = next(
        message
        for message in gateway.requests[1].messages
        if message.role == MessageRole.TOOL
    )
    assert "## Measures and columns its visuals use" in tool_turn.content
    assert GROSS_MARGIN_DAX in tool_turn.content


@pytest.mark.asyncio
async def test_a_follow_up_question_carries_the_conversation(monkeypatch):
    gateway = ScriptedGateway(
        [
            {"tools": [("explain_object", {"object_name": "Gross Margin %"})]},
            {"content": "Gross Margin % divides Gross Profit by Net Sales."},
            {"tools": [("explain_object", {"object_name": "Gross Margin %"})]},
            {"content": "It appears on the Margin Card."},
        ]
    )
    service = _service(gateway, monkeypatch)

    first = await service.generate(AIChatRequest(message="Explain Gross Margin %"))
    await service.generate(
        AIChatRequest(
            message="Which visuals use it?",
            conversation_id=first.conversation_id,
        )
    )

    follow_up = gateway.requests[2].messages
    assert [message.role for message in follow_up[1:4]] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    assert follow_up[1].content == "Explain Gross Margin %"
    assert follow_up[2].content.startswith("Gross Margin % divides")
    assert follow_up[3].content == "Which visuals use it?"


@pytest.mark.asyncio
async def test_conversations_are_scoped_to_the_caller(monkeypatch):
    gateway = ScriptedGateway([{"content": "no tools"}])
    service = _service(gateway, monkeypatch)

    response = await service.generate(
        AIChatRequest(message="what are measures", conversation_id="shared-id")
    )

    assert conversation_history("pbi-token", "shared-id")
    # The same id presented by another principal sees nothing.
    assert conversation_history("someone-else", "shared-id") == []
    assert response.conversation_id == "shared-id"


@pytest.mark.asyncio
async def test_tool_loop_evidence_is_numbered(monkeypatch):
    gateway = ScriptedGateway(
        [
            {"tools": [("explain_object", {"object_name": "Gross Margin %"})]},
            {"content": "Gross Margin % divides Gross Profit by Net Sales."},
        ]
    )

    response = await _service(gateway, monkeypatch).generate(
        AIChatRequest(message="Explain Gross Margin %")
    )

    ids = [item.evidence_id for item in response.evidence]
    assert ids == [f"E{index + 1}" for index in range(len(ids))]


@pytest.mark.asyncio
async def test_explain_lets_the_model_write_the_answer_when_ai_is_on(monkeypatch):
    summary = (
        "Gross Margin % is the share of Net Sales kept as Gross Profit.\\n\\n"
        "DAX\\n    DIVIDE([Gross Profit], [Net Sales])"
    )
    gateway = ScriptedGateway(
        [
            {
                "content": (
                    '{"summary": "' + summary + '", "claims": [{"text": '
                    '"Gross Margin % = DIVIDE([Gross Profit], [Net Sales])", '
                    '"evidence_ids": ["E2"]}]}'
                )
            }
        ]
    )
    context = _context(
        resolved_object=ResolvedObject(
            object_type="measure",
            table_name="Sales",
            object_name="Gross Margin %",
            qualified_name="Sales[Gross Margin %]",
        )
    )
    service = _service(gateway, monkeypatch, context)

    response = await service.explain(
        AIChatRequest(message="Explain Gross Margin %", audience=AudienceType.DEVELOPER)
    )

    assert response.status == AIAnswerStatus.ANSWERED
    assert response.answer.startswith("Gross Margin % is the share")
    assert "\n    DIVIDE([Gross Profit], [Net Sales])" in response.answer
    assert response.usage is not None
    assert len(response.claims) == 1
    # The evidence the model wrote from travels with the answer.
    user_prompt = gateway.requests[0].messages[1].content
    assert "Report open: 'check_remane_app'" in user_prompt
    assert "## Visual impact" in user_prompt


@pytest.mark.asyncio
async def test_explain_falls_back_to_the_deterministic_answer(monkeypatch):
    context = _context(
        resolved_object=ResolvedObject(
            object_type="measure",
            table_name="Sales",
            object_name="Gross Margin %",
            qualified_name="Sales[Gross Margin %]",
        )
    )
    service = _service(
        ScriptedGateway([{"content": "not json at all"}]), monkeypatch, context
    )

    response = await service.explain(AIChatRequest(message="Explain Gross Margin %"))

    assert response.usage is None
    assert GROSS_MARGIN_DAX in response.answer
    assert "Visual impact" in response.answer


def test_a_report_on_a_shared_model_does_not_break_the_graph():
    # The report lives in one workspace and its model in another. The graph
    # rejects report lineage naming a different model home, and that
    # ValueError used to escape the tool as a 500.
    model = sample_semantic_model().model_copy(update={"workspace_id": "ws-model"})
    context = _context(
        parsed_semantic_model=model, semantic_model_workspace_id="ws-model"
    )

    graph = build_context_graph(context)

    assert graph is not None
    assert any(node.node_type == "visual" for node in graph.nodes)
