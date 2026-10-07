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
from collections.abc import Iterable, Mapping
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
        group, "10 years"): text a claim may repeat, digits and all."""
        asked = [
            f"{v:g} {ASKED_WITH_UNIT[k]}" if isinstance(v, (int, float)) else v
            for k, v in self.arguments.items()
            if isinstance(v, str)
            or (k in ASKED_WITH_UNIT and isinstance(v, (int, float)) and not isinstance(v, bool))
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


# What each lookup takes. Anything else is refused: an argument is text a claim may repeat.
ARGUMENTS: dict[str, frozenset[str]] = {
    "chance_of_being_built": frozenset({"place", "project_type", "mw", "within_years", "group"}),
    "realistic_mw_ahead": frozenset({"place", "site"}),
    "list_projects": frozenset({"place", "site", "status", "rules", "project_type"}),
}
# Numbers a lookup is asked for, with the unit they may be repeated with ("within 10 years"):
# on its own, "10" could be passed off as any number.
ASKED_WITH_UNIT = {"within_years": "years", "mw": "MW"}

# Each dataset, and the view that reads only its rows (ADR 0001).
VIEWS = {"caiso_raw": "caiso_projects", "lbnl": "lbnl_projects"}
# A project (``p``) connected at one of a list of places.
AT_PLACES = (
    "EXISTS (SELECT 1 FROM project_places pp WHERE pp.source = p.source "
    "AND pp.native_id = p.native_id AND pp.place = ANY(%s))"
)

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
    # The comparison group a person chose (an Adjustment). It replaces the one a chance
    # lookup would pick, wherever that lookup offers it.
    comparison_group: str | None = None
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
        unknown = set(arguments) - ARGUMENTS[tool]
        if unknown:
            raise LookupRefused(
                f"{tool} doesn't take {sorted(unknown)}; it takes {sorted(ARGUMENTS[tool])}."
            )
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

    def leave(self, native_ids: frozenset[str]) -> None:
        """Leave these projects out of every lookup from now on (an Adjustment)."""
        self.leave_out = self.leave_out | native_ids

    def compare_with(self, group: str) -> None:
        """Use this comparison group for the chances from now on (an Adjustment). Only a
        group a chance lookup in this assessment offered can be chosen."""
        offered = self.comparison_groups()
        if group not in offered:
            raise ValueError(
                f"No comparison group called {group!r} in this assessment. "
                + (
                    "The groups are: " + "; ".join(offered)
                    if offered
                    else "Look up chance_of_being_built first: it lists the groups."
                )
            )
        self.comparison_group = group

    def comparison_groups(self) -> list[str]:
        """Every comparison group the chance lookups so far offered, most specific first."""
        offered: dict[str, None] = {}
        for lookup in self.log.values():
            for group in lookup.notes.get("comparison_groups_to_choose_from", ()):
                offered[group] = None
        return list(offered)

    def waiting_since(self, site: str, year: int) -> list[str]:
        """Projects at a site still waiting that joined the queue in ``year`` or earlier."""
        return [
            str(r[0])
            for r in self.conn.execute(
                "SELECT p.native_id FROM caiso_projects p WHERE p.status = 'Active' "
                f"AND extract(year FROM p.q_date) <= %s AND {AT_PLACES} ORDER BY 1",
                (year, places_at(self.conn, site=site)),
            ).fetchall()
        ]

    def rows_in(self, source: str, ids: Iterable[str]) -> set[str]:
        """Which of these ids are rows of ``source``."""
        found = self.conn.execute(
            f"SELECT native_id FROM {VIEWS[source]} WHERE native_id = ANY(%s)", (sorted(ids),)
        ).fetchall()
        return {str(r[0]) for r in found}

    def column_in(self, source: str, column: str, ids: Iterable[str]) -> dict[str, object]:
        """One column of the operator's file, read from the database for these rows."""
        assert column in COLUMNS and COLUMNS[column].from_the_data  # never a name from the model
        found = self.conn.execute(
            f"SELECT native_id, {column} FROM {VIEWS[source]} WHERE native_id = ANY(%s)",
            (sorted(ids),),
        ).fetchall()
        return {str(native_id): x for native_id, x in found}

    # --- the lookups ---

    def _chance(self, asked: dict[str, Any]) -> _Result:
        within = float(asked["within_years"])
        project_type = ProjectType(asked["project_type"]) if asked.get("project_type") else None
        mw = float(asked["mw"]) if asked.get("mw") is not None and project_type else None
        place = asked.get("place")
        odds = odds_for(
            self.conn,
            within_years=within,
            project_type=project_type,
            mw=mw,
            place=place,
            leave_out=self.leave_out,
        )
        offered = {g.description for g in odds.ladder}
        wanted = self.comparison_group if self.comparison_group in offered else asked.get("group")
        if wanted:
            chosen = next((g for g in odds.ladder if g.description == wanted), None)
            if chosen is None:
                raise LookupError(
                    f"No comparison group called {wanted!r}. The groups are: "
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

    def _ahead(self, asked: dict[str, Any]) -> _Result:
        ahead = realistic_mw_ahead(
            self.conn, place=asked.get("place"), site=asked.get("site"), leave_out=self.leave_out
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

    def _list(self, asked: dict[str, Any]) -> _Result:
        status = STATUSES.get(str(asked.get("status")))
        if status is None:
            raise LookupError(f"status must be one of {sorted(STATUSES)}.")
        rules = RULES.get(str(asked.get("rules", "any")))
        if rules is None:
            raise LookupError(f"rules must be one of {sorted(RULES)}.")
        places = places_at(self.conn, site=asked.get("site"), place=asked.get("place"))
        parts: list[str] | None = None
        if asked.get("project_type"):
            kind = ProjectType(asked["project_type"])
            parts = sorted(next(p for p, t in TYPE_OF_PARTS.items() if t is kind))
        found = self.conn.execute(
            "SELECT p.native_id, p.mw_to_grid, p.q_date FROM caiso_projects p "
            "WHERE p.status = %s AND " + rules + " "
            f"AND {AT_PLACES} "
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


def places_at(conn: Conn, *, site: str | None = None, place: str | None = None) -> list[str]:
    """One voltage section, or every voltage section of a site."""
    if bool(place) == bool(site):
        raise LookupError("Give exactly one of place or site.")
    if place:
        sql, name = "SELECT place FROM places WHERE place = %s", place
    else:
        sql, name = "SELECT place FROM places WHERE site = %s ORDER BY place", str(site)
    places = [str(r[0]) for r in conn.execute(sql, (name,)).fetchall()]
    if not places:
        raise LookupError(f"No place or site called {name!r}.")
    return places
