"""The number checker, fed correct claims and deliberately broken copies of them.

The checker is plain code that always gives the same answer, so these are ordinary unit
tests of it, run against real lookups on the CAISO files in ``data/``. The correct values
come from hand-written SQL here, not from the lookups or the checker.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from interconnection_agent.assessment import (
    FactualClaim,
    Lookup,
    LookupRefused,
    Lookups,
    Value,
    check,
)
from interconnection_agent.db import connect
from interconnection_agent.load import load_all

Conn = psycopg.Connection[tuple[object, ...]]
ROOT = Path(__file__).resolve().parents[2]
AT_WHIRLWIND = (
    "SELECT native_id, mw_to_grid FROM projects p WHERE p.source = 'caiso_raw' "
    "AND p.status = %s AND p.batch IS DISTINCT FROM 'C15' AND p.native_id IN ("
    "  SELECT native_id FROM project_places JOIN places USING (place) "
    "  WHERE places.site = 'Whirlwind') ORDER BY native_id"
)


@pytest.fixture(scope="module")
def conn() -> Iterator[Conn]:
    with connect() as c:
        c.autocommit = False
        try:
            load_all(ROOT / "data", c)
            yield c
        finally:
            c.rollback()


class Whirlwind:
    """Real lookups at Whirlwind, and the answers worked out by hand."""

    def __init__(self, conn: Conn) -> None:
        self.lookups = Lookups(conn)
        self.waiting = self.lookups.run(
            "list_projects", {"site": "Whirlwind", "status": "waiting", "rules": "old"}
        )
        # Nothing from the 2023 batch has been built yet: an empty list.
        self.built_2023 = self.lookups.run(
            "list_projects", {"site": "Whirlwind", "status": "built", "rules": "2023 batch"}
        )
        self.chance = self.lookups.run(
            "chance_of_being_built", {"within_years": 10, "project_type": "Solar only"}
        )
        found = conn.execute(AT_WHIRLWIND, ("Active",)).fetchall()
        self.mw = {str(native_id): float(str(mw)) for native_id, mw in found}
        withdrawn = conn.execute(AT_WHIRLWIND, ("Withdrawn",)).fetchall()
        self.a_withdrawn_project = str(withdrawn[0][0])
        median = conn.execute(
            "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY mw_to_grid) FROM projects "
            "WHERE source = 'caiso_raw' AND native_id = ANY(%s)",
            (list(self.mw),),
        ).fetchone()
        assert median is not None
        self.median_mw = float(str(median[0]))
        # Berkeley Lab's copy of one of these projects ("CAISO / 1234" for CAISO-1234).
        copies = conn.execute(
            "SELECT native_id FROM projects WHERE source = 'lbnl' AND native_id = ANY(%s)",
            ([f"CAISO / {int(i.removeprefix('CAISO-'))}" for i in self.mw if i[6:].isdigit()],),
        ).fetchall()
        self.lbnl_copy = str(copies[0][0])

    @property
    def rows(self) -> tuple[str, ...]:
        return tuple(sorted(self.mw))


def claim(text: str, *values: Value) -> FactualClaim:
    return FactualClaim("c", text, values)


def from_rows(lookup: Lookup, value: float, unit: str, derivation: str, of: str,
              rows: tuple[str, ...]) -> Value:  # fmt: skip
    return Value(value, unit, derivation, of, "caiso_raw", lookup.tool_call_id, rows)


def quoted(lookup: Lookup, figure: str, value: float, unit: str, derivation: str) -> Value:
    return Value(value, unit, derivation, figure, "caiso_raw", lookup.tool_call_id)


@pytest.fixture(scope="module")
def whirlwind(conn: Conn) -> Whirlwind:
    return Whirlwind(conn)


def correct_claims(w: Whirlwind) -> dict[str, FactualClaim]:
    total = sum(w.mw.values())
    one = w.rows[0]
    chance = w.chance.figures["chance"].value
    return {
        "a count": claim("{0} are waiting.", from_rows(
            w.waiting, len(w.mw), "projects", "count", "projects", w.rows)),
        "a sum, rounded to the nearest 10": claim("{0} is waiting.", from_rows(
            w.waiting, round(total, -1), "MW", "sum", "mw_to_grid", w.rows)),
        "the same decimal written differently": claim("{0} is waiting.", from_rows(
            w.waiting, float(f"{total:.6e}"), "MW", "sum", "mw_to_grid", w.rows)),
        "rows in a different order": claim("{0} is waiting.", from_rows(
            w.waiting, total, "MW", "sum", "mw_to_grid", w.rows[::-1])),
        "a direct quote of one row": claim("One project asks for {0}.", from_rows(
            w.waiting, w.mw[one], "MW", "direct", "mw_to_grid", (one,))),
        "the middle size": claim("The middle one asks for {0}.", from_rows(
            w.waiting, w.median_mw, "MW", "median", "mw_to_grid", w.rows)),
        "a count of nothing, from a lookup that returned nothing": claim(
            "{0} from the 2023 batch have been built.",
            from_rows(w.built_2023, 0, "projects", "count", "projects", ())),
        "a figure, rounded to the whole point": claim(
            "{0} were built within 10 years.",
            quoted(w.chance, "chance", round(chance), "%", "ratio")),
    }  # fmt: skip


def test_correct_claims_pass(whirlwind: Whirlwind) -> None:
    for name, good in correct_claims(whirlwind).items():
        result = check(good, whirlwind.lookups)
        assert result.passed, f"{name}: {result.problems}"
    # What it passes with is the data's number and the rows behind it.
    count = check(correct_claims(whirlwind)["a count"], whirlwind.lookups)
    assert count.worked_out == (len(whirlwind.mw),)
    assert count.rows == (frozenset(whirlwind.mw),)


def test_deliberately_broken_claims_are_all_caught(whirlwind: Whirlwind) -> None:
    w = whirlwind
    good = correct_claims(w)
    total_ = good["rows in a different order"]
    total = total_.values[0]
    direct = good["a direct quote of one row"].values[0]
    chance = good["a figure, rounded to the whole point"].values[0]
    fewer = w.rows[1:]
    extra = (*w.rows, w.a_withdrawn_project)

    def changed(**fields: object) -> FactualClaim:
        return replace(total_, values=(replace(total, **fields),))  # type: ignore[arg-type]

    broken = {
        "a value outside the margin": (
            changed(value=total.value * 1.06), "the data gives"),
        "only some of the returned rows, the arithmetic on them right": (
            changed(value=sum(w.mw[r] for r in fewer), source_row_ids=fewer),
            f"uses {len(fewer)} of the {len(w.rows)} rows"),
        "an extra row: a withdrawn project in a claim about waiting projects": (
            changed(source_row_ids=extra), "didn't return"),
        "MW written as GW without converting": (
            changed(value=total.value / 1000), "the data gives"),
        "a unit with no written margin": (changed(value=total.value / 1000, unit="GW"), "GW"),
        "the wrong derivation (says sum, is a ratio)": (
            replace(good["a figure, rounded to the whole point"],
                    values=(replace(chance, derivation="sum"),)), "is a ratio"),
        "a derivation not on the list": (changed(derivation="average"), "isn't one of"),
        "a Berkeley Lab row cited as caiso_raw": (
            changed(source_row_ids=(*fewer, w.lbnl_copy)), "aren't caiso_raw rows"),
        "CAISO's and Berkeley Lab's copies of a project mixed together": (
            changed(source_row_ids=(*w.rows, w.lbnl_copy)), "didn't return"),
        "a CAISO lookup cited as Berkeley Lab's": (changed(source="lbnl"), "names lbnl"),
        "a number citing no rows": (changed(source_row_ids=()), "cites no rows"),
        "a lookup that isn't in the log": (changed(tool_call_id="tc_999"), "isn't in the log"),
        "a direct quote with the wrong number": (
            replace(good["a direct quote of one row"],
                    values=(replace(direct, value=direct.value + 50),)), "the data gives"),
        "a direct quote of a row the lookup didn't return": (
            replace(good["a direct quote of one row"],
                    values=(replace(direct, source_row_ids=(w.a_withdrawn_project,)),)),
            "isn't one lookup"),
        "a figure citing only some of its rows": (
            replace(good["a figure, rounded to the whole point"],
                    values=(replace(chance, source_row_ids=("CAISO-0001",)),)), "uses"),
        "a count of nothing, from a lookup that lists no projects": (
            claim("{0} are waiting.", from_rows(w.chance, 0, "projects", "count", "projects", ())),
            "cites no rows"),
        "a number the lookup was asked for, used as something else": (
            replace(good["a figure, rounded to the whole point"],
                    text="{0} were built within 10 years, 10% of them early."), "aren't checked"),
        "a number in the sentence that isn't in a slot": (
            replace(total_, text="{0} is waiting, across 40 projects."), "aren't checked"),
        "a slot with no number": (replace(total_, text="{0} and {1} are waiting."), "no number"),
    }  # fmt: skip

    for name, (bad, why) in broken.items():
        result = check(bad, w.lookups)
        assert not result.passed, f"not caught: {name}"
        assert any(why in p for p in result.problems), f"{name}: {result.problems}"


def test_a_lookup_refuses_anything_it_does_not_take(whirlwind: Whirlwind) -> None:
    # Otherwise "note": "1,200" would make 1,200 a name the text may repeat.
    with pytest.raises(LookupRefused, match="note"):
        whirlwind.lookups.run(
            "list_projects", {"site": "Whirlwind", "status": "waiting", "note": "1,200"}
        )
