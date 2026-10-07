"""Answer-key questions: does the real agent pick the right rows and state the right numbers?

The checker proves a number matches the rows its lookup returned. It can't prove the lookup
was the right one: the wrong substation, a missing filter. These cases close part of that
gap. Each asks a question with exactly one right set of rows, worked out here by hand in
plain SQL (never through the agent's lookups, so a shared bug can't make both sides agree),
and grades the agent's own stated numbers and rows against it.

They call the real model, so they need ``ANTHROPIC_API_KEY`` (in ``.env`` or the shell)
and are skipped without it. Each case is one ``ask`` on an assessment with no claims yet,
within the usual spending limits.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest

from interconnection_agent.assessment import (
    Assessment,
    Claude,
    FactualClaim,
    Lookups,
    Project,
    ask,
)
from interconnection_agent.assessment.check import MARGINS
from interconnection_agent.db import connect
from interconnection_agent.load import load_all
from interconnection_agent.settings import Settings, SettingsError, load_settings

Conn = psycopg.Connection[tuple[object, ...]]
ROOT = Path(__file__).resolve().parents[2]

AT_SITE = (
    "p.native_id IN (SELECT native_id FROM project_places JOIN places USING (place) "
    "WHERE places.site = %(site)s)"
)
SOLAR_ONLY = (
    "ARRAY(SELECT r.type FROM project_resources r WHERE r.source = p.source "
    "AND r.native_id = p.native_id) = ARRAY['Solar']"
)


@dataclass(frozen=True)
class Case:
    site: str
    question: str
    # The right rows, by hand: a WHERE clause over caiso_projects p, with %(site)s.
    where: str
    mw: bool  # the answer must also give their MW to grid, added up


CASES = {
    "waiting under the old rules": Case(
        "Whirlwind",
        "How many projects that applied before the 2023 rule change are still waiting at "
        "Whirlwind, and how many MW do they add up to?",
        f"p.status = 'Active' AND p.batch IS DISTINCT FROM 'C15' AND {AT_SITE}",
        mw=True,
    ),
    "the 2023 batch on its own": Case(
        "Whirlwind",
        "How many projects from the 2023 batch are waiting at Whirlwind, and how many MW?",
        f"p.status = 'Active' AND p.batch = 'C15' AND {AT_SITE}",
        mw=True,
    ),
    "a type and an outcome": Case(
        "Birds Landing",
        "How many solar-only projects have withdrawn at Birds Landing?",
        f"p.status = 'Withdrawn' AND {SOLAR_ONLY} AND {AT_SITE}",
        mw=False,
    ),
    "built": Case(
        "Smyrna",
        "How many projects at Smyrna have been built?",
        f"p.status = 'Operational' AND {AT_SITE}",
        mw=False,
    ),
}


@pytest.fixture(scope="module")
def settings() -> Settings:
    try:
        return load_settings(os.environ, ROOT / ".env")
    except SettingsError:
        pytest.skip("Answer-key tests call the real model: set ANTHROPIC_API_KEY to run them.")


@pytest.fixture(scope="module")
def conn(settings: Settings) -> Iterator[Conn]:
    with connect() as c:
        c.autocommit = False
        try:
            load_all(ROOT / "data", c)
            yield c
        finally:
            c.rollback()


@pytest.mark.parametrize("name", CASES)
def test_answer_key_questions_get_the_right_numbers_and_rows(
    name: str, conn: Conn, settings: Settings
) -> None:
    case = CASES[name]
    expected = {
        str(native_id): mw
        for native_id, mw in conn.execute(
            f"SELECT p.native_id, p.mw_to_grid FROM caiso_projects p WHERE {case.where}",
            {"site": case.site},
        ).fetchall()
    }
    assessment = Assessment(case.site, Project(), Lookups(conn), claims=[])

    answer = ask(assessment, Claude(settings), case.question)

    # Each number the agent stated that would be shown, with the rows it rests on (a quoted
    # figure's rows come from its lookup).
    stated = [
        (v, rows)
        for c in answer.claims
        if isinstance(c, FactualClaim) and c.check is not None and c.check.passed
        for v, rows in zip(c.values, c.check.rows, strict=True)
    ]
    assert any(
        v.unit == "projects" and v.value == len(expected) and rows == set(expected)
        for v, rows in stated
    ), f"{name}: no count of exactly the right rows in {stated}"
    if case.mw:
        total = sum(mw for mw in expected.values() if isinstance(mw, float))
        assert any(
            v.unit == "MW" and MARGINS["MW"](v.value, total) and rows == set(expected)
            for v, rows in stated
        ), f"{name}: no MW total of exactly the right rows in {stated}"
