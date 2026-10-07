"""The agent against the real model, once: until this, it had only met the scripted stand-in.

Does Claude, following the writing skill, write an assessment whose numbers pass the checker,
and say plainly when the data can't answer something rather than run on into its spending
limit? Calls the real model, so it needs ``ANTHROPIC_API_KEY`` (in ``.env`` or the shell)
and is skipped without it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from interconnection_agent.assessment import Claude, Project, ask, write_assessment
from interconnection_agent.chances import ProjectType
from interconnection_agent.db import connect
from interconnection_agent.load import load_all
from interconnection_agent.settings import Settings, SettingsError, load_settings

Conn = psycopg.Connection[tuple[object, ...]]
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def settings() -> Settings:
    try:
        return load_settings(os.environ, ROOT / ".env")
    except SettingsError:
        pytest.skip("This test calls the real model: set ANTHROPIC_API_KEY to run it.")


@pytest.fixture(scope="module")
def conn(settings: Settings) -> Iterator[Conn]:
    with connect() as c:
        c.autocommit = False
        try:
            load_all(ROOT / "data", c)
            yield c
        finally:
            c.rollback()


def test_the_real_model_writes_a_checked_assessment_and_says_what_the_data_cant_answer(
    conn: Conn, settings: Settings
) -> None:
    claude = Claude(settings)

    assessment = write_assessment(
        conn,
        claude,
        site="Midway",
        project=Project(ProjectType.SOLAR_BATTERY, 200),
        limits=settings.limits,
    )

    shown = [c for c in assessment.factual_claims if c.check is not None and c.check.passed]
    assert len(shown) >= 3, assessment.rejected
    assert assessment.judgements, "the skill asks for at least one Judgement"

    answer = ask(assessment, claude, "What would this project pay to connect here?")

    assert answer.cant_answer, answer
    assert not answer.claims and answer.proposal is None
