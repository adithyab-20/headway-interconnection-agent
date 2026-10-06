"""What the agent can look up, and the log of every lookup it made.

Each lookup gets an id (``tool_call_id``) and is saved in the log together with every row
it returned (ADR 0003). A number in a Factual Claim names the lookup it came from, and the
checker compares it with what that lookup actually returned.

A lookup returns two kinds of thing:

* **figures**: numbers the tested functions worked out (the chance of being built,
  realistic MW ahead, ...), each with the rows it was worked out from. A claim quotes them.
* **rows**: a list of projects, filtered in SQL (the agent never picks rows out of a wider
  list in its head). A claim can count them, add up or take the middle of a column, or quote
  one row's value; the checker redoes that from the database.

All lookups read CAISO's own file (decision #38). Projects a person has left out (an
Adjustment) are left out of every lookup.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from interconnection_agent.chances import ProjectType, odds_for, realistic_mw_ahead
from interconnection_agent.chances.estimate import NotEnoughHistory
from interconnection_agent.chances.groups import TYPE_OF_PARTS, Conn, data_as_of

SOURCE = "caiso_raw"


class Derivation(StrEnum):
    """How a number was worked out: one of a fixed list (ADR 0003)."""

    DIRECT = "direct"
    SUM = "sum"
    COUNT = "count"
    MEDIAN = "median"
    RATIO = "ratio"


@dataclass(frozen=True)
class Figure:
    """A number a tested function worked out, in the unit it is quoted in."""

    value: float
    unit: str
    derivation: Derivation
    rows: frozenset[str]  # the projects it was worked out from


@dataclass(frozen=True)
class Column:
    unit: str
    # True: read straight from the operator's file, so the checker reads it from the
    # database. False: worked out by a tested function, so it is compared with the log.
    from_the_data: bool


# The columns a lookup's rows can have, and what a claim may do with them.
COLUMNS: dict[str, Column] = {
    "mw_to_grid": Column("MW", from_the_data=True),
    "waited_years": Column("years", from_the_data=False),
    "chance_still_built": Column("%", from_the_data=False),
}


@dataclass(frozen=True)
class Lookup:
    """One lookup, as the log keeps it."""

    tool_call_id: str
    tool: str
    arguments: Mapping[str, Any]
    source: str
    figures: Mapping[str, Figure]
    rows: tuple[Mapping[str, Any], ...]  # each has native_id plus some COLUMNS
    # What the lookup says about its figures: the comparison group it used, the rules its
    # history comes from, ...
    notes: Mapping[str, str | tuple[str, ...]]

    @property
    def row_ids(self) -> frozenset[str]:
        return frozenset(str(r["native_id"]) for r in self.rows)

    @property
    def labels(self) -> frozenset[str]:
        """Names the lookup was asked for or returned ("Whirlwind 230 kV", a comparison
        group, "10" years): text a claim may repeat, digits and all."""
        asked = [
            f"{v:g}" if isinstance(v, float) else str(v)
            for v in self.arguments.values()
            if isinstance(v, (str, int, float)) and not isinstance(v, bool)
        ]
        noted = [x for n in self.notes.values() for x in ((n,) if isinstance(n, str) else n)]
        return frozenset(asked + noted)

    def for_the_model(self) -> str:
        """What the model is sent: everything except the rows behind each figure, which can
        run to thousands (a claim quoting a figure gets them from the log)."""
        return json.dumps(
            {
                "tool_call_id": self.tool_call_id,
                "source": self.source,
                "figures": {
                    name: {
                        "value": round(f.value, 4),
                        "unit": f.unit,
                        "derivation": f.derivation.value,
                        "worked_out_from_projects": len(f.rows),
                    }
                    for name, f in self.figures.items()
                },
                "notes": dict(self.notes),
                "rows": [dict(r) for r in self.rows],
            },
            default=str,
        )


class LookupRefused(ValueError):
    """A lookup was asked for something it can't do; the message goes back to the model."""


STATUSES = {"waiting": "Active", "built": "Operational", "withdrawn": "Withdrawn"}
RULES = {
    "old": "p.batch IS DISTINCT FROM 'C15'",
    "2023 batch": "p.batch IS NOT DISTINCT FROM 'C15'",
    "any": "true",
}


@dataclass
class Lookups:
    """Runs the agent's lookups and keeps the log."""

    conn: Conn
    leave_out: frozenset[str] = frozenset()
    log: dict[str, Lookup] = field(default_factory=dict)

    def run(self, tool: str, arguments: Mapping[str, Any]) -> Lookup:
        """Run a lookup and log it. Raises :class:`LookupRefused` for a request it can't do."""
        runner = {
            "chance_of_being_built": self._chance,
            "realistic_mw_ahead": self._ahead,
            "list_projects": self._list,
        }.get(tool)
        if runner is None:
            raise LookupRefused(f"There is no lookup called {tool!r}.")
        tool_call_id = f"tc_{len(self.log) + 1:03d}"
        try:
            figures, rows, notes = runner(dict(arguments))
        except (LookupError, NotEnoughHistory, ValueError, TypeError) as e:
            raise LookupRefused(str(e)) from e
        lookup = Lookup(
            tool_call_id,
            tool,
            dict(arguments),
            SOURCE,
            figures,
            tuple(rows),
            notes,
        )
        self.log[tool_call_id] = lookup
        return lookup

    def again(self, lookup: Lookup) -> Lookup:
        """Run a logged lookup again (after an Adjustment), as a new entry in the log."""
        return self.run(lookup.tool, lookup.arguments)

    # --- the lookups ---

    def _chance(self, a: dict[str, Any]) -> _Result:
        within = float(a["within_years"])
        project_type = ProjectType(a["project_type"]) if a.get("project_type") else None
        mw = float(a["mw"]) if a.get("mw") is not None and project_type else None
        place = a.get("place")
        odds = odds_for(
            self.conn,
            within_years=within,
            project_type=project_type,
            mw=mw,
            place=place,
            leave_out=self.leave_out,
        )
        if a.get("group"):
            chosen = next((g for g in odds.ladder if g.description == a["group"]), None)
            if chosen is None:
                raise LookupError(
                    f"No comparison group called {a['group']!r}. The groups are: "
                    + "; ".join(g.description for g in odds.ladder)
                )
            odds = odds_for(
                self.conn,
                within_years=within,
                project_type=project_type,
                mw=mw,
                place=place,
                use=chosen,
                leave_out=self.leave_out,
            )
        c = odds.chance
        every = frozenset(r.native_id for r in c.rows)

        def having(outcome: str) -> frozenset[str]:
            return frozenset(r.native_id for r in c.rows if r.outcome.value == outcome)

        figures = {
            "chance": Figure(c.chance * 100, "%", Derivation.RATIO, every),
            "chance_low": Figure(c.likely_range[0] * 100, "%", Derivation.RATIO, every),
            "chance_high": Figure(c.likely_range[1] * 100, "%", Derivation.RATIO, every),
            "past_projects": Figure(c.projects, "projects", Derivation.COUNT, every),
            "built": Figure(c.built, "projects", Derivation.COUNT, having("built")),
            "withdrawn": Figure(c.withdrawn, "projects", Derivation.COUNT, having("withdrawn")),
            "still_waiting": Figure(c.waiting, "projects", Derivation.COUNT, having("waiting")),
        }
        if c.typical_wait_years is not None:
            figures["typical_wait"] = Figure(
                c.typical_wait_years, "years", Derivation.MEDIAN, every
            )
        notes: dict[str, str | tuple[str, ...]] = {
            "comparison_group": odds.used.description,
            "enough_history": (
                "enough history to rely on" if odds.used.enough else "too few projects to rely on"
            ),
            "history_from": odds.history_from,
            "comparison_groups_to_choose_from": tuple(g.description for g in odds.ladder),
        }
        return figures, [], notes

    def _ahead(self, a: dict[str, Any]) -> _Result:
        ahead = realistic_mw_ahead(
            self.conn, place=a.get("place"), site=a.get("site"), leave_out=self.leave_out
        )
        old = frozenset(p.native_id for p in ahead.projects)
        new = frozenset(p.native_id for p in ahead.new_rules_projects)
        figures = {
            "realistic_mw": Figure(ahead.realistic_mw, "MW", Derivation.SUM, old),
            "realistic_mw_low": Figure(ahead.likely_range[0], "MW", Derivation.SUM, old),
            "realistic_mw_high": Figure(ahead.likely_range[1], "MW", Derivation.SUM, old),
            "waiting_mw": Figure(ahead.waiting_mw, "MW", Derivation.SUM, old),
            "waiting_projects": Figure(len(old), "projects", Derivation.COUNT, old),
            "new_rules_mw": Figure(ahead.new_rules_mw, "MW", Derivation.SUM, new),
            "new_rules_projects": Figure(len(new), "projects", Derivation.COUNT, new),
        }
        rows = [
            {
                "native_id": p.native_id,
                "mw_to_grid": p.mw_to_grid,
                "waited_years": round(p.waited_years, 2),
                "chance_still_built": round((p.chance_still_built or 0) * 100, 2),
            }
            for p in ahead.projects
        ]
        notes: dict[str, str | tuple[str, ...]] = {
            "realistic_mw": "counts only projects that applied before the 2023 rule change",
            "new_rules_mw": "the 2023 batch's waiting MW: chance not known, never added in",
            "data_as_of": data_as_of(self.conn).isoformat(),
            "not_counted": tuple(f"{native_id}: {why}" for native_id, why in ahead.left_out),
        }
        return figures, rows, notes

    def _list(self, a: dict[str, Any]) -> _Result:
        status = STATUSES.get(str(a.get("status")))
        if status is None:
            raise LookupError(f"status must be one of {sorted(STATUSES)}.")
        rules = RULES.get(str(a.get("rules", "any")))
        if rules is None:
            raise LookupError(f"rules must be one of {sorted(RULES)}.")
        places = _places(self.conn, a)
        parts: list[str] | None = None
        if a.get("project_type"):
            kind = ProjectType(a["project_type"])
            parts = sorted(next(p for p, t in TYPE_OF_PARTS.items() if t is kind))
        found = self.conn.execute(
            "SELECT p.native_id, p.mw_to_grid, p.q_date FROM caiso_projects p "
            "WHERE p.status = %s AND " + rules + " "
            "AND EXISTS (SELECT 1 FROM project_places pp WHERE pp.source = p.source "
            "            AND pp.native_id = p.native_id AND pp.place = ANY(%s)) "
            "AND (%s::text[] IS NULL OR ARRAY(SELECT r.type FROM project_resources r "
            "     WHERE r.source = p.source AND r.native_id = p.native_id ORDER BY r.type) "
            "     = %s::text[]) "
            "AND NOT (p.native_id = ANY(%s)) ORDER BY p.native_id",
            (status, places, parts, parts, sorted(self.leave_out)),
        ).fetchall()
        rows = []
        for native_id, mw, q_date in found:
            assert q_date is None or isinstance(q_date, datetime.date)
            rows.append(
                {
                    "native_id": str(native_id),
                    "mw_to_grid": float(mw) if isinstance(mw, (int, float)) else None,
                    "joined_queue": q_date.isoformat() if q_date else None,
                }
            )
        return {}, rows, {}


_Result = tuple[dict[str, Figure], list[dict[str, Any]], dict[str, str | tuple[str, ...]]]


def _places(conn: Conn, a: Mapping[str, Any]) -> list[str]:
    if bool(a.get("place")) == bool(a.get("site")):
        raise LookupError("Give exactly one of place or site.")
    if a.get("place"):
        sql, name = "SELECT place FROM places WHERE place = %s", a["place"]
    else:
        sql, name = "SELECT place FROM places WHERE site = %s ORDER BY place", a["site"]
    places = [str(r[0]) for r in conn.execute(sql, (name,)).fetchall()]
    if not places:
        raise LookupError(f"No place or site called {name!r}.")
    return places


def places_at(conn: Conn, site: str) -> list[str]:
    """The voltage sections of a site, lowest voltage first."""
    return _places(conn, {"site": site})
