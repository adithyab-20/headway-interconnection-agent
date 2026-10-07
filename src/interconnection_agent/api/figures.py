"""What the website shows: the figures for the landing page, the map and a substation page.

Every figure comes from the tested functions in ``interconnection_agent.chances``; this
module only gathers them and attaches the rows they were worked out from, so the page can
show any number's source rows. The two slow ones (every substation's realistic MW ahead,
and the landing page's statewide odds) are worked out once per load of the data and kept.
"""

from __future__ import annotations

import datetime
import math
import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

from interconnection_agent.chances import (
    MWAhead,
    NotEnoughHistory,
    ProjectType,
    chance_of_reaching_operation,
    odds_for,
    outcomes_by_year,
    realistic_mw_ahead,
)
from interconnection_agent.chances.groups import (
    SIZE_BANDS,
    TYPE_OF_PARTS,
    ComparisonGroup,
    Conn,
    data_as_of,
    history,
    members,
)

# The years the page offers a chance for ("built within 3, 5, 7 or 10 years").
YEARS_OFFERED = (3, 5, 7, 10)
# A size inside each band, for the landing page's "Try a project type" (MW to grid).
SIZE_FOR_BAND = {"under 50 MW": 25.0, "50-150 MW": 100.0, "150-300 MW": 200.0}
SIZE_FOR_BAND["300 MW and over"] = 400.0
STATUS = {"Active": "waiting", "Operational": "built", "Withdrawn": "withdrawn"}


def _type_of(parts: Iterable[str]) -> str | None:
    kind = TYPE_OF_PARTS.get(frozenset(parts))
    return str(kind) if kind else None


# --- Kept per load of the data --------------------------------------------------------

_kept: dict[tuple[str, datetime.date], Any] = {}
_keeping = threading.Lock()


def _kept_for(conn: Conn, name: str, work_out: Any) -> Any:
    key = (name, data_as_of(conn))
    with _keeping:
        if key not in _kept:
            _kept[key] = work_out(conn)
        return _kept[key]


def forget_kept() -> None:
    """Drop what was kept, so the next request works it out again (after a reload)."""
    with _keeping:
        _kept.clear()


# --- The map -------------------------------------------------------------------------


def sites(conn: Conn) -> dict[str, Any]:
    """Every substation with projects waiting, with its realistic MW ahead and where it is.
    Takes about 15 seconds the first time; kept afterwards."""
    return dict(_kept_for(conn, "sites", _sites))


def _sites(conn: Conn) -> dict[str, Any]:
    names = [
        str(r[0])
        for r in conn.execute(
            "SELECT DISTINCT pl.site FROM caiso_projects p "
            "JOIN project_places pp USING (source, native_id) JOIN places pl USING (place) "
            "WHERE p.status = 'Active' ORDER BY 1"
        ).fetchall()
    ]
    found = []
    for name in names:
        about = _about_site(conn, name)
        ahead = realistic_mw_ahead(conn, site=name)
        found.append({**about, **_ahead_totals(ahead)})
    return {"as_of": data_as_of(conn).isoformat(), "sites": found}


def _about_site(conn: Conn, site: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT place, voltage_kv, county, state, latitude, longitude, positioned_by, "
        "position_source FROM places WHERE site = %s ORDER BY voltage_kv DESC NULLS LAST",
        (site,),
    ).fetchall()
    if not rows:
        raise LookupError(f"No substation called {site!r}.")
    counties = Counter((r[2], r[3]) for r in rows if r[2])
    (county, state), _ = (counties.most_common(1) or [((None, None), 0)])[0]
    first = rows[0]
    return {
        "site": site,
        "county": county,
        "state": state,
        "latitude": first[4],
        "longitude": first[5],
        "positioned_by": first[6],
        "position_source": first[7],
        "places": [{"place": r[0], "voltage_kv": r[1]} for r in rows],
    }


def _ahead_totals(ahead: MWAhead) -> dict[str, Any]:
    return {
        "realistic_mw": ahead.realistic_mw,
        "realistic_range": list(ahead.likely_range),
        "waiting_mw": ahead.waiting_mw,
        "waiting_projects": len(ahead.projects),
        "new_rules_mw": ahead.new_rules_mw,
        "new_rules_projects": len(ahead.new_rules_projects),
    }


# --- The landing page ----------------------------------------------------------------


def overview(conn: Conn) -> dict[str, Any]:
    """Every past project by the year it applied and what happened to it, and the
    statewide odds for each project type and size. Kept once worked out."""
    return dict(_kept_for(conn, "overview", _overview))


def _overview(conn: Conn) -> dict[str, Any]:
    years: dict[int, Counter[str]] = {}
    for year, status, new_rules, count in conn.execute(
        "SELECT extract(year FROM q_date)::int, status, batch IS NOT DISTINCT FROM 'C15', "
        "count(*) FROM caiso_projects WHERE q_date IS NOT NULL GROUP BY 1, 2, 3"
    ).fetchall():
        assert isinstance(year, int) and isinstance(count, int)
        outcome = STATUS[str(status)]
        key = f"new_rules_{outcome}" if new_rules else outcome
        years.setdefault(year, Counter())[key] += count
    types: dict[str, dict[str, Any]] = {}
    for kind in ProjectType:
        types[str(kind)] = {}
        for band in SIZE_BANDS:
            types[str(kind)][band.label] = _statewide(conn, kind, SIZE_FOR_BAND[band.label])
    return {
        "as_of": data_as_of(conn).isoformat(),
        "years": {str(y): dict(c) for y, c in sorted(years.items())},
        "types": types,
    }


def _statewide(conn: Conn, kind: ProjectType, mw: float) -> dict[str, Any]:
    try:
        odds = odds_for(conn, within_years=10, project_type=kind, mw=mw)
    except NotEnoughHistory as e:
        return {"refused": str(e)}
    (year_10,) = outcomes_by_year(members(history(conn), odds.used), [10])
    return {
        "group": odds.used.description,
        "chance": odds.chance.chance,
        "range": list(odds.chance.likely_range),
        "withdrawn": year_10.withdrawn,
        "still_waiting": year_10.still_waiting,
        "projects": odds.chance.projects,
        "typical_wait": odds.chance.typical_wait_years,
    }


# --- A substation --------------------------------------------------------------------


def site_detail(conn: Conn, site: str, leave_out: frozenset[str] = frozenset()) -> dict[str, Any]:
    """One substation: where it is, who's ahead (without the projects a person left out),
    every project that ever applied there, and the upgrades and bottlenecks around it."""
    about = _about_site(conn, site)
    ahead = realistic_mw_ahead(conn, site=site, leave_out=leave_out)
    projects = _projects_at(conn, site)
    by_id = {p["id"]: p for p in projects}

    def waiting(p: Any) -> dict[str, Any]:
        known = by_id.get(p.native_id, {})
        return {
            "id": p.native_id,
            "mw": p.mw_to_grid,
            "waited_years": p.waited_years,
            "chance": p.chance_still_built,
            "on_a_line": p.on_a_line,
            "compared_with": p.compared_with.description if p.compared_with else None,
            "applied": known.get("applied"),
            "types": known.get("types", []),
            "type": known.get("type"),
            "furthest_step": known.get("furthest_step"),
        }

    return {
        **about,
        "as_of": data_as_of(conn).isoformat(),
        "left_out": sorted(leave_out),
        "ahead": {
            **_ahead_totals(ahead),
            "projects": [waiting(p) for p in ahead.projects],
            "new_rules": [waiting(p) for p in ahead.new_rules_projects],
            "not_counted": [{"id": i, "why": why} for i, why in ahead.left_out],
        },
        "projects": projects,
        "upgrades": _upgrades_at(conn, site),
        "bottlenecks": _bottlenecks_at(conn, site),
    }


_PROJECT_ROWS = (
    "SELECT p.native_id, p.status, p.q_date, p.outcome_date, p.outcome_date_estimated, "
    "  p.mw_to_grid, p.batch IS NOT DISTINCT FROM 'C15', p.furthest_step, "
    "  ARRAY(SELECT r.type FROM project_resources r "
    "        WHERE r.source = p.source AND r.native_id = p.native_id ORDER BY r.type) "
    "FROM caiso_projects p "
)


def _project_row(row: tuple[object, ...], as_of: datetime.date) -> dict[str, Any]:
    native_id, status, q_date, outcome_date, estimated, mw, new_rules, step, parts = row
    assert isinstance(parts, list)
    end = as_of if status == "Active" else outcome_date
    years = (
        max(0, (end - q_date).days) / 365.25
        if isinstance(q_date, datetime.date) and isinstance(end, datetime.date)
        else None
    )
    return {
        "id": str(native_id),
        "status": STATUS.get(str(status), str(status)),
        "applied": q_date.isoformat() if isinstance(q_date, datetime.date) else None,
        "ended": outcome_date.isoformat() if isinstance(outcome_date, datetime.date) else None,
        "date_estimated": bool(estimated),
        "years": years,
        "mw": float(mw) if isinstance(mw, (int, float)) else None,
        "rules": "2023 batch" if new_rules else "old",
        "furthest_step": step,
        "types": [str(t) for t in parts],
        "type": _type_of(str(t) for t in parts),
    }


def _projects_at(conn: Conn, site: str) -> list[dict[str, Any]]:
    as_of = data_as_of(conn)
    found = conn.execute(
        _PROJECT_ROWS + "WHERE EXISTS (SELECT 1 FROM project_places pp JOIN places pl "
        "USING (place) WHERE pp.source = p.source AND pp.native_id = p.native_id "
        "AND pl.site = %s) ORDER BY p.native_id",
        (site,),
    ).fetchall()
    return [_project_row(r, as_of) for r in found]


def rows(conn: Conn, ids: Iterable[str]) -> list[dict[str, Any]]:
    """The source rows behind a number: each project as the operator's file has it."""
    as_of = data_as_of(conn)
    found = conn.execute(
        _PROJECT_ROWS + "WHERE p.native_id = ANY(%s) ORDER BY p.native_id", (sorted(set(ids)),)
    ).fetchall()
    return [_project_row(r, as_of) for r in found]


def _upgrades_at(conn: Conn, site: str) -> list[dict[str, Any]]:
    found = conn.execute(
        "SELECT u.plan_id, u.name, u.utility, u.expected_finish_year, u.cost_low_musd, "
        "  u.cost_high_musd, u.source, array_agg(DISTINCT up.place ORDER BY up.place) "
        "FROM upgrades u JOIN upgrade_places up USING (plan_id) JOIN places pl USING (place) "
        "WHERE pl.site = %s GROUP BY u.plan_id ORDER BY u.expected_finish_year NULLS LAST, 1",
        (site,),
    ).fetchall()
    keys = ("plan_id", "name", "utility", "year", "cost_low_musd", "cost_high_musd", "source")
    return [{**dict(zip(keys, r[:7], strict=True)), "places": r[7]} for r in found]


def _bottlenecks_at(conn: Conn, site: str) -> list[dict[str, Any]]:
    found = conn.execute(
        "SELECT b.bottleneck, b.room_left_mw, b.added_mw, b.cost_musd_2022, b.listed_in, "
        "  b.costed_in, array_agg(DISTINCT pb.place ORDER BY pb.place) "
        "FROM place_bottlenecks pb JOIN bottlenecks b USING (bottleneck) "
        "JOIN places pl USING (place) WHERE pl.site = %s "
        "GROUP BY b.bottleneck ORDER BY b.room_left_mw NULLS LAST, 1",
        (site,),
    ).fetchall()
    shown = []
    for name, room, added, cost, listed_in, costed_in, places in found:
        per_kw = (
            float(cost) * 1_000 / float(added)
            if isinstance(cost, (int, float)) and isinstance(added, (int, float)) and added
            else None
        )
        shown.append(
            {
                "bottleneck": name,
                "room_left_mw": room,
                "cost_per_kw": per_kw,
                "listed_in": listed_in,
                "costed_in": costed_in,
                "places": places,
            }
        )
    return shown


# --- The odds for a project ----------------------------------------------------------


def odds(
    conn: Conn,
    *,
    place: str,
    project_type: ProjectType | None,
    mw: float | None,
    within_years: int = 10,
    group: str | None = None,
    leave_out: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """The chance of being built, the typical wait and the year-by-year picture for a
    project at ``place``, from the comparison group the rule picks (or ``group``, a
    description from the ladder). Every rung of the ladder comes with its counts."""
    mw = mw if project_type else None
    picked = odds_for(
        conn,
        within_years=within_years,
        project_type=project_type,
        mw=mw,
        place=place,
        leave_out=leave_out,
    )
    if group and group != picked.used.description:
        chosen = next((g for g in picked.ladder if g.description == group), None)
        if chosen is None:
            raise LookupError(f"No comparison group called {group!r}.")
        picked = odds_for(
            conn,
            within_years=within_years,
            project_type=project_type,
            mw=mw,
            place=place,
            use=chosen,
            leave_out=leave_out,
        )
    records = history(conn, leave_out=leave_out)
    used = members(records, picked.used)
    longest = picked.used.longest_watched_years
    return {
        "used": picked.used.description,
        "history_from": picked.history_from,
        "by_years": {str(n): _chance(used, n) for n in YEARS_OFFERED},
        "ladder": [
            _rung(g, members(records, g), within_years, g == picked.used) for g in picked.ladder
        ],
        "curve": [
            {**asdict(y), "built_range": list(y.built_range)}
            for y in outcomes_by_year(used, [n / 2 for n in range(math.floor(longest) * 2 + 1)])
        ],
        "rows": rows(conn, (p.native_id for p in used)),
    }


def _chance(group: list[Any], within_years: float) -> dict[str, Any]:
    try:
        c = chance_of_reaching_operation(group, within_years)
    except NotEnoughHistory as e:
        return {"refused": str(e)}
    return {
        "chance": c.chance,
        "range": list(c.likely_range),
        "typical_wait": c.typical_wait_years,
        "wait_range": list(c.typical_wait_range) if c.typical_wait_range else None,
        "projects": c.projects,
        "built": c.built,
        "withdrawn": c.withdrawn,
        "waiting": c.waiting,
        "watched": c.watched_to_n_years,
    }


def _rung(g: ComparisonGroup, group: list[Any], within_years: int, used: bool) -> dict[str, Any]:
    return {
        "description": g.description,
        "area_kind": str(g.area_kind),
        "area": g.area,
        "projects": g.projects,
        "resolved": g.resolved,
        "built": g.built,
        "enough": g.enough,
        "used": used,
        "chance": _chance(group, within_years) if g.enough or used else None,
        "ids": sorted(p.native_id for p in group),  # the rows behind its counts
    }
