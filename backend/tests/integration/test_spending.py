"""The site's monthly spend limit: every model call is priced and counted, whichever model.

These run against the real database. The model is a stand-in that reports the tokens it
was asked to; prices come from Anthropic's price list.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from anthropic.types.beta import BetaMessage

from interconnection_agent.db import connect
from interconnection_agent.spending import Metered, SpendLimitReached, spent_this_month

# 15 October 2026, noon in California.
MID_OCTOBER = datetime(2026, 10, 15, 19, 0, tzinfo=UTC)


class Reporting:
    """A stand-in model whose every reply reports the same token usage."""

    def __init__(self, **usage: int) -> None:
        self.usage = {"input_tokens": 0, "output_tokens": 0, **usage}
        self.calls = 0

    def create(self, **request: Any) -> BetaMessage:
        self.calls += 1
        return BetaMessage.model_validate(
            {
                "id": f"msg_{self.calls}",
                "type": "message",
                "role": "assistant",
                "model": "stand-in",
                "content": [{"type": "text", "text": "Done."}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": self.usage,
            }
        )


@pytest.fixture(autouse=True)
def _no_spend_yet() -> Iterator[None]:
    with connect() as c:
        c.execute("DELETE FROM model_spend")
    yield
    with connect() as c:
        c.execute("DELETE FROM model_spend")


def metered(model: Reporting, priced_as: str, limit: float, at: datetime = MID_OCTOBER) -> Metered:
    return Metered(model, priced_as=priced_as, limit_usd=limit, connect=connect, clock=lambda: at)


def spent(at: datetime = MID_OCTOBER) -> float:
    with connect() as c:
        return spent_this_month(c, at)


def test_once_the_months_spend_reaches_the_limit_the_next_call_is_refused() -> None:
    # 10,000 input tokens on Sonnet 5.5 at $2 per million: $0.02.
    model = Reporting(input_tokens=10_000)
    sonnet = metered(model, "claude-sonnet-5-5", limit=0.01)

    sonnet.create(messages=[])
    with pytest.raises(SpendLimitReached, match="spending limit for the month"):
        sonnet.create(messages=[])

    assert model.calls == 1
    assert spent() == pytest.approx(0.02)


def test_every_models_calls_count_toward_the_same_limit() -> None:
    metered(Reporting(input_tokens=10_000), "claude-sonnet-5-5", limit=1.0).create(messages=[])

    haiku = Reporting(input_tokens=1_000)
    with pytest.raises(SpendLimitReached):
        metered(haiku, "claude-haiku-5-5", limit=0.02).create(messages=[])
    assert haiku.calls == 0


def test_every_kind_of_token_is_priced_at_the_models_rates() -> None:
    # Opus 5.5: $4 input, $20 output, $5 cache writes, $0.20 cache reads, per million.
    opus = Reporting(
        input_tokens=100_000,
        output_tokens=10_000,
        cache_creation_input_tokens=20_000,
        cache_read_input_tokens=500_000,
    )
    metered(opus, "claude-opus-5-5", limit=10.0).create(messages=[])

    assert spent() == pytest.approx(0.40 + 0.20 + 0.10 + 0.10)


def test_a_haiku_prompt_over_100000_tokens_is_priced_at_the_higher_rate() -> None:
    # 60,000 + 50,000 = 110,000 prompt tokens: $0.50 input and $0.05 cache reads per million.
    long_prompt = Reporting(input_tokens=60_000, cache_read_input_tokens=50_000)
    metered(long_prompt, "claude-haiku-5-5", limit=10.0).create(messages=[])
    assert spent() == pytest.approx(0.03 + 0.0025)

    with connect() as c:
        c.execute("DELETE FROM model_spend")
    # 90,000 prompt tokens: $0.10 input per million.
    metered(Reporting(input_tokens=90_000), "claude-haiku-5-5", limit=10.0).create(messages=[])
    assert spent() == pytest.approx(0.009)


def test_the_limit_starts_again_on_the_first_of_the_month_california_time() -> None:
    # 31 October, 11:30 pm in California, which is already 1 November in UTC.
    last_thing_in_october = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    metered(Reporting(input_tokens=10_000), "claude-sonnet-5-5", 1.0, last_thing_in_october).create(
        messages=[]
    )
    # 1 November, 12:30 am in California.
    first_thing_in_november = datetime(2026, 11, 1, 7, 30, tzinfo=UTC)

    assert spent(last_thing_in_october) == pytest.approx(0.02)
    assert spent(first_thing_in_november) == 0
    november = Reporting(input_tokens=10_000)
    metered(november, "claude-sonnet-5-5", 0.01, first_thing_in_november).create(messages=[])
    assert november.calls == 1
