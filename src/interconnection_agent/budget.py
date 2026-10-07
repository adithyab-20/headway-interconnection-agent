"""Hard limits on how much one assessment may spend on the model.

An agent that loops does not just give a wrong answer; it keeps billing. These limits
turn that into a failed request: once an assessment has made too many model calls or used
too many tokens, the next step raises instead of quietly continuing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    """The most one assessment may use. Each field has an environment variable to change it."""

    max_turns: int = 10
    """Model calls allowed per assessment (``AGENT_MAX_TURNS``)."""

    max_tokens_per_assessment: int = 200_000
    """Input plus output tokens, summed over every call (``AGENT_MAX_TOKENS_PER_ASSESSMENT``).

    A call's size is only known once it returns, so the call that crosses this limit is
    still paid for. The total can therefore go over by at most one call, and then stops.
    """

    max_output_tokens_per_call: int = 16_000
    """The ``max_tokens`` sent with each request (``AGENT_MAX_OUTPUT_TOKENS_PER_CALL``)."""


class BudgetExceeded(RuntimeError):
    """An assessment hit one of its limits and was stopped."""


class TurnLimitExceeded(BudgetExceeded):
    """The assessment already made as many model calls as it is allowed."""


class TokenLimitExceeded(BudgetExceeded):
    """The assessment used more tokens, in total, than it is allowed."""


class OutputLimitExceeded(BudgetExceeded):
    """One model call wrote more than the per-call limit allows."""


class ResponseTruncated(BudgetExceeded):
    """The model stopped mid-answer because it ran out of room, so the answer is incomplete."""


# Stop reasons meaning the model was cut off rather than finished. A cut-off answer is
# usually half-written JSON or a sentence that stops mid-way; using it would be wrong.
CUT_OFF_STOP_REASONS: frozenset[str] = frozenset({"max_tokens", "model_context_window_exceeded"})


class AssessmentBudget:
    """Tracks one assessment's model usage against its ``Limits``.

    The agent calls ``before_call`` before every request to the model and ``record``
    with the usage from every response. Either one raises as soon as a limit is crossed.
    """

    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.turns_used = 0
        self.tokens_used = 0

    @property
    def calls_left(self) -> int:
        """Model calls this assessment may still make."""
        return max(0, self.limits.max_turns - self.turns_used)

    def before_call(self) -> None:
        """Raise if one more model call would go past a limit."""
        if self.turns_used >= self.limits.max_turns:
            raise TurnLimitExceeded(
                f"Assessment stopped: it has made {self.turns_used} model calls and the "
                f"limit is {self.limits.max_turns}. Raise AGENT_MAX_TURNS to allow more."
            )
        # Checked here as well as in ``record`` so that catching the error from ``record``
        # and carrying on does not get round the limit.
        if self.tokens_used >= self.limits.max_tokens_per_assessment:
            raise self._token_limit_error()

    def record(self, *, input_tokens: int, output_tokens: int, stop_reason: str) -> None:
        """Count one finished model call."""
        self.turns_used += 1
        self.tokens_used += input_tokens + output_tokens
        if self.tokens_used > self.limits.max_tokens_per_assessment:
            raise self._token_limit_error()
        if output_tokens > self.limits.max_output_tokens_per_call:
            raise OutputLimitExceeded(
                f"Assessment stopped: one model call wrote {output_tokens:,} output tokens and "
                f"the limit is {self.limits.max_output_tokens_per_call:,}. The caller must send "
                "Limits.max_output_tokens_per_call as the request's max_tokens."
            )
        if stop_reason in CUT_OFF_STOP_REASONS:
            raise ResponseTruncated(
                f"Assessment stopped: the model's answer was cut off ({stop_reason}) after "
                f"{output_tokens:,} output tokens, so it is incomplete. The per-call limit is "
                f"{self.limits.max_output_tokens_per_call:,}; raise "
                "AGENT_MAX_OUTPUT_TOKENS_PER_CALL to allow longer answers."
            )

    def _token_limit_error(self) -> TokenLimitExceeded:
        return TokenLimitExceeded(
            f"Assessment stopped: it has used {self.tokens_used:,} tokens and the limit is "
            f"{self.limits.max_tokens_per_assessment:,}. "
            "Raise AGENT_MAX_TOKENS_PER_ASSESSMENT to allow more."
        )
