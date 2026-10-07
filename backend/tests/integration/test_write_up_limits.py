"""The public site's limits on starting write-ups: per visitor, per day, and the off switch.

These call the API the way the website does, against the real database, with small limits
and a stand-in model that declines at once. Visitors are told apart by the address the
website's host passes on (``X-Forwarded-For``).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from anthropic.types.beta import BetaMessage
from fastapi.testclient import TestClient

from interconnection_agent.api import create_app
from interconnection_agent.db import connect
from interconnection_agent.settings import SiteLimits

WRITE_UP = {"site": "Midway"}
# 15 October 2026, noon in California.
NOON = datetime(2026, 10, 15, 19, 0, tzinfo=UTC)


class Declining:
    def create(self, **request: Any) -> BetaMessage:
        return BetaMessage.model_validate(
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "stand-in",
                "content": [],
                "stop_reason": "refusal",
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        )


@pytest.fixture(autouse=True)
def _nothing_started_or_spent() -> Iterator[None]:
    def clear() -> None:
        with connect() as c:
            c.execute("DELETE FROM write_up_starts")
            c.execute("DELETE FROM model_spend")

    clear()
    yield
    clear()


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def site(limits: SiteLimits, clock: Clock | None = None, *, model: bool = True) -> TestClient:
    the_model = Declining()
    return TestClient(
        create_app(
            lambda: the_model if model else None,
            site_limits=limits,
            clock=clock or Clock(NOON),
            warm=False,
        )
    )


def start(client: TestClient, visitor: str) -> Any:
    return client.post("/api/assessments", json=WRITE_UP, headers={"X-Forwarded-For": visitor})


def test_a_visitors_fourth_write_up_of_the_day_is_refused() -> None:
    client = site(SiteLimits(write_ups_per_visitor_per_day=3, write_ups_per_day=20))

    assert [start(client, "203.0.113.7").status_code for _ in range(3)] == [202, 202, 202]
    r = start(client, "203.0.113.7")

    assert r.status_code == 429
    assert r.json()["detail"] == (
        "You've started 3 write-ups today, the most one visitor can start in a day. You can "
        "start another after midnight, California time. Everything else on the page still "
        "works."
    )


def test_another_visitor_can_still_start_one() -> None:
    client = site(SiteLimits(write_ups_per_visitor_per_day=1, write_ups_per_day=20))
    start(client, "203.0.113.7")

    assert start(client, "203.0.113.7").status_code == 429
    assert start(client, "198.51.100.4").status_code == 202


def test_once_the_site_has_started_its_write_ups_for_the_day_everyone_is_refused() -> None:
    client = site(SiteLimits(write_ups_per_visitor_per_day=5, write_ups_per_day=2))
    start(client, "203.0.113.7")
    start(client, "198.51.100.4")

    r = start(client, "192.0.2.9")

    assert r.status_code == 429
    assert r.json()["detail"] == (
        "The site has written as many write-ups as it can today. More can be started after "
        "midnight, California time. Everything else on the page still works."
    )


def test_a_limit_of_zero_turns_write_ups_off() -> None:
    client = site(SiteLimits(write_ups_per_day=0))

    r = start(client, "203.0.113.7")

    assert r.status_code == 503
    assert r.json()["detail"] == (
        "Write-ups are turned off on this site for now. Everything else on the page works."
    )


def test_once_the_months_spend_limit_is_reached_a_write_up_is_refused_at_once() -> None:
    client = site(SiteLimits(spend_per_month_usd=0))

    r = start(client, "203.0.113.7")

    assert r.status_code == 429
    assert "spending limit for the month" in r.json()["detail"]


def test_without_a_key_nothing_is_counted_against_anyone() -> None:
    limits = SiteLimits(write_ups_per_visitor_per_day=1, write_ups_per_day=1)
    assert start(site(limits, model=False), "203.0.113.7").status_code == 503
    assert start(site(limits, model=False), "203.0.113.7").status_code == 503

    assert start(site(limits), "203.0.113.7").status_code == 202


def test_the_count_starts_again_after_midnight_california_time() -> None:
    # 15 October, 11:30 pm in California.
    clock = Clock(datetime(2026, 10, 16, 6, 30, tzinfo=UTC))
    client = site(SiteLimits(write_ups_per_visitor_per_day=1, write_ups_per_day=20), clock)
    start(client, "203.0.113.7")
    assert start(client, "203.0.113.7").status_code == 429

    # 16 October, 12:10 am in California.
    clock.now = datetime(2026, 10, 16, 7, 10, tzinfo=UTC)

    assert start(client, "203.0.113.7").status_code == 202
