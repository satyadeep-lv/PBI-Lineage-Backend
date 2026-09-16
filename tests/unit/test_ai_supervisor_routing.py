import pytest

from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import AIAnswerStatus, AIIntent
from app.ai.models.requests import AIChatContext
from app.ai.orchestration.intent import classify_intent
from app.ai.orchestration.supervisor import Supervisor


@pytest.mark.parametrize(
    ("message", "context", "expected_intent"),
    [
        (
            "Explain this measure",
            AIChatContext(object_type="measure"),
            AIIntent.MEASURE_EXPLANATION,
        ),
        (
            "How is Gross Margin calculated?",
            None,
            AIIntent.MEASURE_EXPLANATION,
        ),
        (
            "What happens if this measure changes?",
            AIChatContext(object_type="measure"),
            AIIntent.OBJECT_IMPACT,
        ),
        (
            "What depends on Sales[Revenue]?",
            AIChatContext(object_type="column"),
            AIIntent.OBJECT_IMPACT,
        ),
        (
            "Explain this report and where its data comes from",
            AIChatContext(object_type="report"),
            AIIntent.REPORT_INFORMATION,
        ),
        (
            "Which semantic model powers this report?",
            None,
            AIIntent.REPORT_INFORMATION,
        ),
        (
            "What's the weather today?",
            None,
            AIIntent.OUT_OF_SCOPE,
        ),
    ],
)
def test_classify_intent_is_deterministic(message, context, expected_intent):
    assert classify_intent(message, context) == expected_intent


def test_supervisor_routes_out_of_scope_without_an_agent():
    bundle = Supervisor().handle(
        question="What's the weather today?",
        chat_context=None,
        resolved_context=ResolvedAIContext(),
    )

    assert bundle.status == AIAnswerStatus.OUT_OF_SCOPE
    assert bundle.can_answer is False
    assert bundle.agent is None
    assert bundle.evidence == []


def test_supervisor_routes_measure_question_to_measure_agent():
    bundle = Supervisor().handle(
        question="Explain this measure",
        chat_context=AIChatContext(object_type="measure"),
        resolved_context=ResolvedAIContext(),
    )

    assert bundle.agent == "measure_agent"


def test_supervisor_routes_impact_question_to_impact_agent():
    bundle = Supervisor().handle(
        question="What depends on this?",
        chat_context=AIChatContext(object_type="column"),
        resolved_context=ResolvedAIContext(),
    )

    assert bundle.agent == "impact_agent"


def test_supervisor_routes_report_question_to_report_agent():
    bundle = Supervisor().handle(
        question="Explain this report",
        chat_context=AIChatContext(object_type="report"),
        resolved_context=ResolvedAIContext(),
    )

    assert bundle.agent == "report_agent"
