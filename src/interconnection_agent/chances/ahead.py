"""Realistic MW ahead: the MW waiting at a substation, each project counted only by its chance
of still being built given how long it has already waited.

A waiting project is compared with the history across California (decision #26: there's too
little history at any one substation), in the most specific group of its type and size that
has enough. A project connecting partway along a line counts at both of the line's ends, but
only once in any one number.

The 2023 batch applied under the new rules, which no past project went through, so nothing
says how likely those projects are to be built. Their MW is given beside realistic MW ahead,
never weighted and never added in.
"""

from __future__ import annotations

import datetime
import random
from dataclasses import dataclass

from interconnection_agent.chances.estimate import RESAMPLES, SEED, ChanceGivenWait, middle_95
from interconnection_agent.chances.groups import (
    DAYS_PER_YEAR,
    SOURCE,
    ComparisonGroup,
    Conn,
    comparison_ladder,
    data_as_of,
    history,
    members,
    usable_groups,
)


@dataclass(frozen=True)
class WaitingProject:
    source: str
    native_id: str
    mw_to_grid: float
    waited_years: float
    on_a_line: bool  # connects partway along a line, so counts at both its ends
    # None for the 2023 batch: no history under the new rules.
    chance_still_built: float | None
    compared_with: ComparisonGroup | None  # the past projects the chance was worked out from


@dataclass(frozen=True)
class MWAhead:
    where: str
    realistic_mw: float
    # 95% of the totals from the comparison groups redrawn at random (a bootstrap).
    likely_range: tuple[float, float]
    waiting_mw: float  # the same projects' MW, unweighted
    projects: tuple[WaitingProject, ...]  # old rules, each with its chance
    # Waiting under the new rules (2023 batch): chance not known, so never weighted.
    new_rules_mw: float
    new_rules_projects: tuple[WaitingProject, ...]
    # Waiting projects that can't be counted, and why (no MW to grid, no queue date).
    left_out: tuple[tuple[str, str], ...]


_PLACES_IN = {
    "place": "SELECT place FROM places WHERE place = %s",
    "site": "SELECT place FROM places WHERE site = %s",
    "bottleneck": "SELECT place FROM place_bottlenecks WHERE bottleneck = %s",
}


def realistic_mw_ahead(
    conn: Conn,
    *,
    place: str | None = None,
    site: str | None = None,
    bottleneck: str | None = None,
    leave_out: frozenset[str] = frozenset(),
) -> MWAhead:
    """Realistic MW ahead at one voltage section, at a whole site, or behind a bottleneck.
    ``leave_out`` names projects a person has left out (an Adjustment): they are neither
    counted as waiting nor part of the history the chances come from."""
    given = {"place": place, "site": site, "bottleneck": bottleneck}
    chosen = [(kind, name) for kind, name in given.items() if name]
    if len(chosen) != 1:
        raise ValueError("Give exactly one of place, site or bottleneck.")
    kind, name = chosen[0]
    places = [str(r[0]) for r in conn.execute(_PLACES_IN[kind], (name,)).fetchall()]
    if not places:
        raise LookupError(f"No {kind} called {name!r}.")

    as_of = data_as_of(conn)
    waiting = conn.execute(
        "SELECT p.native_id, p.batch IS NOT DISTINCT FROM 'C15', p.mw_to_grid, p.q_date, "
        "  bool_or(pp.role = 'line_end') "
        "FROM caiso_projects p JOIN project_places pp USING (source, native_id) "
        "WHERE p.status = 'Active' AND pp.place = ANY(%s) AND NOT (p.native_id = ANY(%s)) "
        "GROUP BY 1, 2, 3, 4 ORDER BY 1",
        (places, sorted(leave_out)),
    ).fetchall()

    records = history(conn, leave_out=leave_out)
    by_id = {r.past.native_id: r for r in records}
    estimates: dict[ComparisonGroup, ChanceGivenWait] = {}
    old_rules: list[WaitingProject] = []
    new_rules: list[WaitingProject] = []
    left_out: list[tuple[str, str]] = []
    for native_id, new_batch, mw, q_date, on_a_line in waiting:
        if not isinstance(mw, (int, float)):
            left_out.append((str(native_id), "no MW to grid in the operator's file"))
            continue
        if not isinstance(q_date, datetime.date):
            left_out.append((str(native_id), "no queue date in the operator's file"))
            continue
        if new_batch:
            waited = (as_of - q_date).days / DAYS_PER_YEAR
            new_rules.append(
                WaitingProject(
                    SOURCE, str(native_id), float(mw), waited, bool(on_a_line), None, None
                )
            )
            continue
        record = by_id[str(native_id)]
        # Across California: the project's type and size, its type, or all projects.
        size_mw = record.mw if record.project_type else None
        ladder = comparison_ladder(records, conn, record.project_type, size_mw, None)
        group = usable_groups(ladder)[0]
        if group not in estimates:
            estimates[group] = ChanceGivenWait(members(records, group))
        old_rules.append(
            WaitingProject(
                SOURCE,
                str(native_id),
                float(mw),
                record.past.years,
                bool(on_a_line),
                estimates[group].after(record.past.years),
                group,
            )
        )
    return MWAhead(
        where=name or "",
        realistic_mw=sum(p.mw_to_grid * (p.chance_still_built or 0) for p in old_rules),
        likely_range=_likely_range(old_rules, estimates),
        waiting_mw=sum(p.mw_to_grid for p in old_rules),
        projects=tuple(old_rules),
        new_rules_mw=sum(p.mw_to_grid for p in new_rules),
        new_rules_projects=tuple(new_rules),
        left_out=tuple(left_out),
    )


def _likely_range(
    projects: list[WaitingProject], estimates: dict[ComparisonGroup, ChanceGivenWait]
) -> tuple[float, float]:
    """Redraw each comparison group at random, add up again, and keep the middle 95%."""
    if not projects:
        return 0.0, 0.0
    rng = random.Random(SEED)
    totals = []
    for _ in range(RESAMPLES):
        redrawn = {group: estimate.redrawn(rng) for group, estimate in estimates.items()}
        totals.append(
            sum(
                p.mw_to_grid * redrawn[p.compared_with].after(p.waited_years)
                for p in projects
                if p.compared_with is not None
            )
        )
    return middle_95(totals)
