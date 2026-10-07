"""Writing an assessment through the API: started at once, then checked on until it's done.

Writing takes a minute or two, longer than the website's host waits for one request, so
starting a write-up returns straight away and the page checks back. These call the API the
way the website does, against the loaded database, with a stand-in for the model that
holds each write-up until the test lets it go.

Needs the data loaded (``load_all``); skipped otherwise.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from anthropic.types.beta import BetaMessage
from fastapi.testclient import TestClient

from interconnection_agent.api import create_app
from interconnection_agent.db import connect

SITE = "Midway"
SOLAR_100_MW = {"site": SITE, "project_type": "Solar only", "mw": 100}


def _loaded() -> bool:
    try:
        with connect() as c:
            return (
                c.execute("SELECT 1 FROM data_as_of WHERE source = 'caiso_raw'").fetchone()
                is not None
            )
    except psycopg.Error:
        return False


class HeldModel:
    """Holds every request until ``release`` is called, then declines to write."""

    def __init__(self) -> None:
        self.released = threading.Event()

    def release(self) -> None:
        self.released.set()

    def create(self, **request: Any) -> BetaMessage:
        self.released.wait(timeout=30)
        return BetaMessage.model_validate(
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "stand-in",
                "content": [],
                "stop_reason": "refusal",
                "stop_sequence": None,
                "usage": {"input_tokens": 1_000, "output_tokens": 0},
            }
        )


@pytest.fixture
def model() -> Iterator[HeldModel]:
    held = HeldModel()
    yield held
    held.release()


@pytest.fixture
def client(model: HeldModel) -> Iterator[TestClient]:
    if not _loaded():
        pytest.skip("The data isn't loaded: run load_all first.")
    with TestClient(create_app(lambda: model, warm=False)) as c:
        yield c


def test_starting_a_write_up_returns_at_once_and_says_it_is_being_written(
    client: TestClient,
) -> None:
    started = time.monotonic()
    r = client.post("/api/assessments", json=SOLAR_100_MW)

    assert time.monotonic() - started < 5
    assert r.status_code == 202
    assert r.json()["status"] == "writing"
    assert r.json()["id"]


def test_checking_on_a_write_up_while_it_is_written_says_it_is_still_being_written(
    client: TestClient,
) -> None:
    started = client.post("/api/assessments", json=SOLAR_100_MW).json()

    r = client.get(f"/api/assessments/{started['id']}")

    assert r.status_code == 202
    assert r.json() == {"id": started["id"], "status": "writing"}


def test_a_write_up_that_fails_says_why_when_checked_on(
    client: TestClient, model: HeldModel
) -> None:
    started = client.post("/api/assessments", json=SOLAR_100_MW).json()
    model.release()

    r = _when_written(client, started["id"])

    assert r.status_code == 502
    assert r.json() == {"detail": "The model declined to write this assessment."}


def test_a_write_up_still_being_written_cannot_be_changed_yet(client: TestClient) -> None:
    started = client.post("/api/assessments", json=SOLAR_100_MW).json()

    r = client.post(f"/api/assessments/{started['id']}/finalise")

    assert r.status_code == 409
    assert r.json() == {"detail": "This write-up is still being written."}


def _when_written(client: TestClient, assessment_id: str) -> Any:
    """Check on a write-up, as the page does, until it's no longer being written."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        r = client.get(f"/api/assessments/{assessment_id}")
        if r.status_code != 202:
            return r
        time.sleep(0.05)
    raise AssertionError("The write-up was still being written after 30 seconds.")
