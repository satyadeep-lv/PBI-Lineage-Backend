import pytest

from app.ai.models.context import ResolvedAIContext
from app.ai.models.messages import ModelToolCall
from app.ai.models.requests import ModelRequest
from app.ai.models.responses import ModelResponse, TokenUsage
from app.ai.orchestration.tool_loop import (
    MAX_TOOL_ROUNDS,
    ToolLoopUnavailableError,
    run_tool_loop,
)
from app.ai.tools.registry import TOOL_REGISTRY, tool_schemas
from tests.unit.ai_fixtures import (
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_semantic_model,
)


class ScriptedGateway:
    """Drives the loop deterministically, standing in for a live provider."""

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        step = self.script.pop(0) if self.script else {"content": "done"}

        return ModelResponse(
            content=step.get("content", ""),
            provider="scripted",
            model="scripted-model",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            tool_calls=[
                ModelToolCall(id=f"call-{index}", name=name, arguments=arguments)
                for index, (name, arguments) in enumerate(step.get("tools", []))
            ],
        )

    def stream(self, request):  # pragma: no cover - not used by the loop
        raise NotImplementedError


def _context(**overrides) -> ResolvedAIContext:
    defaults = dict(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        parsed_semantic_model=sample_semantic_model(),
    )
    defaults.update(overrides)
    return ResolvedAIContext(**defaults)


@pytest.mark.asyncio
async def test_the_model_chooses_a_tool_and_answers_from_its_evidence():
    gateway = ScriptedGateway(
        [
            {"tools": [("explain_object", {"object_name": "Gross Margin %"})]},
            {"content": "Gross Margin % divides Gross Profit by Net Sales."},
        ]
    )

    result = await run_tool_loop(
        gateway,
        question="explain Gross Margin %",
        context=_context(),
    )

    assert result.answer.startswith("Gross Margin %")
    assert result.evidence
    assert [record.tool for record in result.trace] == ["explain_object"]
    assert result.trace[0].status == "completed"
    assert result.trace[0].evidence_count == len(result.evidence)


@pytest.mark.asyncio
async def test_an_object_the_ui_never_resolved_can_still_be_named():
    # The fixed path needs `resolved_object` set by the UI first; naming the
    # measure in the tool call is what makes an unprompted question work.
    gateway = ScriptedGateway(
        [
            {"tools": [("explain_object", {"object_name": "Gross Profit"})]},
            {"content": "Gross Profit sums CostAmount."},
        ]
    )

    result = await run_tool_loop(
        gateway,
        question="what is Gross Profit",
        context=_context(),
    )

    definitions = [
        item for item in result.evidence if str(item.fact_type) == "definition"
    ]
    assert definitions
    assert definitions[0].object_name == "Gross Profit"


@pytest.mark.asyncio
async def test_tools_are_offered_with_schemas_and_forced_on_the_first_round():
    gateway = ScriptedGateway([{"content": "answer"}])

    await run_tool_loop(gateway, question="hello", context=_context())

    first = gateway.requests[0]
    assert first.require_tool is True
    names = {tool["name"] for tool in first.tools}
    assert "explain_object" in names and "model_overview" in names
    assert all("parameters" in tool for tool in first.tools)


@pytest.mark.asyncio
async def test_report_tools_are_hidden_when_no_report_is_in_context():
    # A tool whose context is missing is never offered, so the model cannot
    # choose something that could only return nothing.
    schemas = {tool["name"] for tool in tool_schemas(_context())}

    assert "report_visuals" not in schemas
    assert "model_overview" in schemas


@pytest.mark.asyncio
async def test_an_unknown_tool_name_is_reported_not_executed():
    gateway = ScriptedGateway(
        [
            {"tools": [("drop_everything", {})]},
            {"content": "I could not do that."},
        ]
    )

    result = await run_tool_loop(gateway, question="x", context=_context())

    assert result.trace[0].status == "unknown_tool"
    assert result.evidence == []


@pytest.mark.asyncio
async def test_a_repeated_identical_call_is_short_circuited():
    gateway = ScriptedGateway(
        [
            {"tools": [("model_overview", {})]},
            {"tools": [("model_overview", {})]},
            {"content": "done"},
        ]
    )

    result = await run_tool_loop(gateway, question="x", context=_context())

    assert [record.status for record in result.trace] == ["completed", "repeated"]


@pytest.mark.asyncio
async def test_the_loop_stops_at_its_round_limit():
    gateway = ScriptedGateway(
        [{"tools": [("search_model", {"query": f"q{index}"})]} for index in range(20)]
    )

    result = await run_tool_loop(gateway, question="x", context=_context())

    assert result.rounds <= MAX_TOOL_ROUNDS + 1
    assert result.stopped_reason is not None


@pytest.mark.asyncio
async def test_no_tools_available_raises_so_the_caller_can_fall_back():
    with pytest.raises(ToolLoopUnavailableError):
        await run_tool_loop(
            ScriptedGateway([]),
            question="x",
            context=ResolvedAIContext(),
        )


def test_every_registered_tool_is_read_only_and_self_describing():
    for name, tool in TOOL_REGISTRY.items():
        assert tool.description.strip()
        assert tool.parameters["type"] == "object"
        # No tool may accept free-form extra arguments.
        assert tool.parameters["additionalProperties"] is False
        assert name == tool.name


@pytest.mark.asyncio
async def test_ai_service_prefers_the_tool_loop_and_reports_the_trace(monkeypatch):
    from app.ai.models.requests import AIChatRequest
    from app.ai.services.ai_service import AIService
    from app.core.config import Settings

    gateway = ScriptedGateway(
        [
            {"tools": [("explain_object", {"object_name": "Gross Margin %"})]},
            {"content": "Gross Margin % divides Gross Profit by Net Sales."},
        ]
    )
    service = AIService(
        settings=Settings(ai_enabled=True, ai_provider="fake"),
        gateway=gateway,
    )

    async def fake_context(request):
        return _context()

    monkeypatch.setattr(service, "_resolved_context", fake_context)

    response = await service.generate(AIChatRequest(message="explain Gross Margin %"))

    assert response.agent == "tool_loop"
    assert response.answer.startswith("Gross Margin %")
    assert [call.tool for call in response.tool_trace] == ["explain_object"]
    assert response.evidence


@pytest.mark.asyncio
async def test_ai_service_falls_back_when_the_model_answers_without_evidence(
    monkeypatch,
):
    # A model answer with no tool evidence behind it is precisely what this
    # system must not return, so the deterministic path takes over.
    from app.ai.models.requests import AIChatRequest
    from app.ai.services.ai_service import AIService
    from app.core.config import Settings

    service = AIService(
        settings=Settings(ai_enabled=True, ai_provider="fake"),
        gateway=ScriptedGateway([{"content": "I think it is about sales."}]),
    )

    async def fake_context(request):
        return _context()

    monkeypatch.setattr(service, "_resolved_context", fake_context)

    response = await service.generate(AIChatRequest(message="what are measures"))

    assert response.agent != "tool_loop"
    assert response.tool_trace == []
    assert "Gross Margin %" in response.answer
