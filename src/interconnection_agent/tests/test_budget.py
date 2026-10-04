"""Unit tests for :mod:`interconnection_agent.budget`.

The budget never talks to the API. A test plays the agent's part: it asks permission
before each model call and reports the usage the response came back with.
"""

import pytest

from interconnection_agent.budget import (
    AssessmentBudget,
    Limits,
    OutputLimitExceeded,
    ResponseTruncated,
    TokenLimitExceeded,
    TurnLimitExceeded,
)


def make_call(budget: AssessmentBudget, input_tokens: int = 100, output_tokens: int = 50) -> None:
    """One model call as the agent will make it: ask first, then report usage."""
    budget.before_call()
    budget.record(input_tokens=input_tokens, output_tokens=output_tokens, stop_reason="end_turn")


def test_call_past_the_turn_limit_is_refused() -> None:
    budget = AssessmentBudget(Limits(max_turns=3))
    for _ in range(3):
        make_call(budget)

    with pytest.raises(TurnLimitExceeded, match=r"limit is 3.*AGENT_MAX_TURNS"):
        budget.before_call()


def test_going_over_the_token_total_stops_the_assessment() -> None:
    budget = AssessmentBudget(Limits(max_tokens_per_assessment=1_000))
    make_call(budget, input_tokens=600, output_tokens=300)

    with pytest.raises(
        TokenLimitExceeded, match=r"1,050 tokens.*limit is 1,000.*AGENT_MAX_TOKENS_PER_ASSESSMENT"
    ):
        make_call(budget, input_tokens=100, output_tokens=50)


def test_no_further_calls_after_the_token_total_is_used_up() -> None:
    budget = AssessmentBudget(Limits(max_tokens_per_assessment=1_000))
    with pytest.raises(TokenLimitExceeded):
        make_call(budget, input_tokens=900, output_tokens=200)

    with pytest.raises(TokenLimitExceeded):
        budget.before_call()


def test_usage_exactly_at_the_limit_is_allowed() -> None:
    budget = AssessmentBudget(Limits(max_turns=2, max_tokens_per_assessment=1_000))

    make_call(budget, input_tokens=400, output_tokens=100)
    make_call(budget, input_tokens=400, output_tokens=100)

    assert (budget.turns_used, budget.tokens_used) == (2, 1_000)


@pytest.mark.parametrize("stop_reason", ["max_tokens", "model_context_window_exceeded"])
def test_a_cut_off_response_is_an_error_not_a_short_answer(stop_reason: str) -> None:
    budget = AssessmentBudget(Limits(max_output_tokens_per_call=4_000))
    budget.before_call()

    with pytest.raises(ResponseTruncated, match=r"cut off.*AGENT_MAX_OUTPUT_TOKENS_PER_CALL"):
        budget.record(input_tokens=1_000, output_tokens=4_000, stop_reason=stop_reason)

    # The cut-off call was still paid for, so it still counts.
    assert (budget.turns_used, budget.tokens_used) == (1, 5_000)


@pytest.mark.parametrize("stop_reason", ["end_turn", "tool_use", "stop_sequence"])
def test_normal_endings_are_not_treated_as_cut_off(stop_reason: str) -> None:
    budget = AssessmentBudget(Limits())
    budget.before_call()

    budget.record(input_tokens=1_000, output_tokens=200, stop_reason=stop_reason)

    assert budget.turns_used == 1


def test_an_answer_longer_than_the_per_call_limit_is_refused() -> None:
    # The API never returns more than the max_tokens it was sent, so this only happens if
    # the caller forgot to send the limit. That mistake should fail loudly, not cost money.
    budget = AssessmentBudget(Limits(max_output_tokens_per_call=4_000))
    budget.before_call()

    with pytest.raises(OutputLimitExceeded, match=r"4,500 output tokens.*limit is 4,000"):
        budget.record(input_tokens=1_000, output_tokens=4_500, stop_reason="end_turn")
