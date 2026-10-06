"""The spending limits stop an assessment; they never let it quietly run on.

The budget never talks to the API. A test plays the agent's part: it asks before each model
call and reports the usage the response came back with.
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
    budget.before_call()
    budget.record(input_tokens=input_tokens, output_tokens=output_tokens, stop_reason="end_turn")


def test_calls_up_to_the_turn_limit_are_allowed_and_the_next_is_refused() -> None:
    budget = AssessmentBudget(Limits(max_turns=3))
    for _ in range(3):
        make_call(budget)

    with pytest.raises(TurnLimitExceeded, match=r"limit is 3.*AGENT_MAX_TURNS"):
        budget.before_call()


def test_going_over_the_token_total_stops_the_assessment_for_good() -> None:
    budget = AssessmentBudget(Limits(max_tokens_per_assessment=1_000))
    make_call(budget, input_tokens=400, output_tokens=100)
    make_call(budget, input_tokens=400, output_tokens=100)  # exactly at the limit: allowed

    with pytest.raises(TokenLimitExceeded, match=r"1,000 tokens.*AGENT_MAX_TOKENS_PER_ASSESSMENT"):
        budget.before_call()  # and catching it doesn't get round it


@pytest.mark.parametrize("stop_reason", ["max_tokens", "model_context_window_exceeded"])
def test_an_unfinished_or_oversized_answer_is_an_error_and_still_counts(stop_reason: str) -> None:
    budget = AssessmentBudget(Limits(max_output_tokens_per_call=4_000))
    budget.before_call()
    with pytest.raises(ResponseTruncated, match=r"cut off.*AGENT_MAX_OUTPUT_TOKENS_PER_CALL"):
        budget.record(input_tokens=1_000, output_tokens=4_000, stop_reason=stop_reason)
    assert (budget.turns_used, budget.tokens_used) == (1, 5_000)  # it was still paid for

    budget.before_call()
    with pytest.raises(OutputLimitExceeded, match=r"4,500 output tokens.*limit is 4,000"):
        budget.record(input_tokens=0, output_tokens=4_500, stop_reason="end_turn")


@pytest.mark.parametrize("stop_reason", ["end_turn", "tool_use", "stop_sequence"])
def test_normal_endings_are_not_treated_as_cut_off(stop_reason: str) -> None:
    budget = AssessmentBudget(Limits())
    budget.before_call()
    budget.record(input_tokens=1_000, output_tokens=200, stop_reason=stop_reason)
    assert budget.turns_used == 1
