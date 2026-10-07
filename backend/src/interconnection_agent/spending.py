"""What the site spends on the model, and the monthly limit on it.

Every model call is priced from the tokens it used, at its model's rates, and kept in the
database. Before each call, the month's total so far is checked against the limit, so the
site as a whole can't spend more than it's allowed, whichever model it uses. A call's cost
is only known once it returns, so each call already under way can take the total over by
at most that one call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import psycopg
from anthropic.types.beta import BetaMessage, BetaUsage

if TYPE_CHECKING:
    from interconnection_agent.assessment import Model

Conn = psycopg.Connection[tuple[object, ...]]

# The month starts at midnight on the 1st in California, where the queue is.
TIME_ZONE = "America/Los_Angeles"

SPENT_IT = (
    "This site has reached its spending limit for the month, so it can't write or answer "
    "anything new until the 1st. Everything else on the page still works."
)


@dataclass(frozen=True)
class Prices:
    """US dollars per million tokens (platform.claude.com/docs/en/about-claude/pricing)."""

    input: float
    output: float
    cache_write: float
    cache_read: float
    long_prompt: Prices | None = None
    """Haiku 5.5's prices for a prompt over ``LONG_PROMPT`` tokens; others have none."""


LONG_PROMPT = 100_000

# The models the site can use, with their prices.
PRICES: dict[str, Prices] = {
    "claude-sonnet-5-5": Prices(input=2.00, output=10.00, cache_write=2.50, cache_read=0.20),
    "claude-haiku-5-5": Prices(
        input=0.10,
        output=0.50,
        cache_write=0.125,
        cache_read=0.01,
        long_prompt=Prices(input=0.50, output=2.50, cache_write=0.625, cache_read=0.05),
    ),
    "claude-opus-5-5": Prices(input=4.00, output=20.00, cache_write=5.00, cache_read=0.20),
}


class SpendLimitReached(RuntimeError):
    """The site has spent its limit for the month."""


def cost_of(model: str, usage: BetaUsage) -> float:
    """What one call cost in US dollars, at ``model``'s rates."""
    written = usage.cache_creation_input_tokens or 0
    read = usage.cache_read_input_tokens or 0
    prices = PRICES[model]
    if prices.long_prompt and usage.input_tokens + written + read > LONG_PROMPT:
        prices = prices.long_prompt
    per_token = (
        usage.input_tokens * prices.input
        + usage.output_tokens * prices.output
        + written * prices.cache_write
        + read * prices.cache_read
    )
    return per_token / 1_000_000


def spent_this_month(conn: Conn, now: datetime) -> float:
    """What the site has spent since the start of ``now``'s month, California time."""
    row = conn.execute(
        "SELECT coalesce(sum(usd), 0)::float8 FROM model_spend "
        "WHERE at >= date_trunc('month', %(now)s AT TIME ZONE %(tz)s) AT TIME ZONE %(tz)s",
        {"now": now, "tz": TIME_ZONE},
    ).fetchone()
    assert row is not None
    return float(row[0])  # type: ignore[arg-type]


def check_spend(conn: Conn, limit_usd: float, now: datetime) -> None:
    """Raise if the site has spent its limit for ``now``'s month."""
    if spent_this_month(conn, now) >= limit_usd:
        raise SpendLimitReached(SPENT_IT)


class Metered:
    """A model whose every call is checked against the monthly limit, then priced and kept.

    ``priced_as`` is the model the settings chose; a reply served by another priced model
    (a fallback) is priced at that model's rates instead.
    """

    def __init__(
        self,
        model: Model,
        *,
        priced_as: str,
        limit_usd: float,
        connect: Callable[[], Conn],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._model = model
        self._priced_as = priced_as
        self._limit_usd = limit_usd
        self._connect = connect
        self._clock = clock

    def create(self, **request: Any) -> BetaMessage:
        with self._connect() as conn:
            check_spend(conn, self._limit_usd, self._clock())
        response = self._model.create(**request)
        served_by = response.model if response.model in PRICES else self._priced_as
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO model_spend (at, model, usd) VALUES (%s, %s, %s)",
                (self._clock(), served_by, cost_of(served_by, response.usage)),
            )
        return response
