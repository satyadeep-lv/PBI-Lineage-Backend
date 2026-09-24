import pytest

from app.ai.composition.deterministic_renderer import DeterministicAnswerRenderer
from app.ai.models.context import ResolvedAIContext, ResolvedObject
from app.ai.models.enums import AIAnswerStatus, AIIntent, AudienceType
from app.ai.models.requests import AIChatContext
from app.ai.orchestration.intent import classify_intent
from app.ai.orchestration.supervisor import Supervisor
from tests.unit.ai_fixtures import (
    SEMANTIC_MODEL_ID,
    WORKSPACE_ID,
    sample_semantic_model,
)


def _context(**overrides) -> ResolvedAIContext:
    defaults = dict(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        parsed_semantic_model=sample_semantic_model(),
    )
    defaults.update(overrides)
    return ResolvedAIContext(**defaults)


@pytest.mark.parametrize(
    "question",
    [
        "what are measures",
        "how many reports we have",
        "list the tables",
        "which measures exist",
    ],
)
def test_inventory_questions_route_to_the_model_agent(question):
    assert classify_intent(question, None) == AIIntent.SEMANTIC_MODEL_INFORMATION


@pytest.mark.parametrize(
    "question",
    [
        "Explain what I'm looking at",
        "What can Power AI help me with here?",
        "give me an overview",
    ],
)
def test_orientation_questions_route_to_the_model_agent(question):
    assert classify_intent(question, None) == AIIntent.SEMANTIC_MODEL_INFORMATION


def test_an_inventory_question_wins_over_a_selected_measure():
    # "what measures are there" is an inventory question even while a
    # measure happens to be selected in the UI.
    intent = classify_intent(
        "what measures are there",
        AIChatContext(object_type="measure"),
    )

    assert intent == AIIntent.SEMANTIC_MODEL_INFORMATION


def test_explaining_a_selected_measure_still_routes_to_the_measure_agent():
    intent = classify_intent(
        "explain this",
        AIChatContext(object_type="measure"),
    )

    assert intent == AIIntent.MEASURE_EXPLANATION


@pytest.mark.parametrize(
    "question",
    [
        "what are measures",
        "Explain what I'm looking at",
        "What can Power AI help me with here?",
    ],
)
def test_previously_refused_questions_now_answer(question):
    bundle = Supervisor().handle(
        question=question,
        chat_context=None,
        resolved_context=_context(),
    )

    assert bundle.status == AIAnswerStatus.ANSWERED
    answer = DeterministicAnswerRenderer.render(bundle, AudienceType.BUSINESS)
    # Names, not just counts, and not a raw dict dump.
    assert "Gross Margin %" in answer
    assert "{" not in answer


def test_an_unresolvable_object_falls_back_to_what_is_known():
    # Asking about a measure that does not exist used to end at
    # "insufficient evidence"; it now says what the model does contain.
    bundle = Supervisor().handle(
        question="explain this",
        chat_context=AIChatContext(object_type="measure"),
        resolved_context=_context(
            resolved_object=ResolvedObject(
                object_type="measure",
                table_name="Sales",
                object_name="Does Not Exist",
                qualified_name="Sales[Does Not Exist]",
            )
        ),
    )

    assert bundle.status == AIAnswerStatus.ANSWERED
    assert bundle.missing_information  # still says what it could not resolve
    assert bundle.evidence


def test_no_model_in_context_still_says_what_is_missing():
    bundle = Supervisor().handle(
        question="what are measures",
        chat_context=None,
        resolved_context=ResolvedAIContext(),
    )

    assert bundle.status == AIAnswerStatus.INSUFFICIENT_EVIDENCE
    assert bundle.missing_information
