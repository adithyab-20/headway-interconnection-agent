"""Comparison groups: which past projects a new project is compared with.

The history is every project in CAISO's main report, which all applied under the rules
before 2023. The 2023 batch applied under the new rules and is left out of it (decision
#39). A project with an outcome but no date at all can't be placed in time; the load
reports those, and they're left out here too.

A fixed rule picks the group (decision #40): the most specific one that still has enough
past projects. It steps back from type and size at the project's own voltage section, to its
site, to each bottleneck area it sits behind (narrowest first), to its county, then to type
and size across California, type alone, and finally all projects.

A figure for N years also needs a project in the group watched for N years. To reach that
far it keeps widening the place (and drops the size), but it never changes the project type
just to find a longer history: it refuses instead (decision #38: no battery has 15 years).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum

import psycopg

from interconnection_agent.chances.estimate import (
    Chance,
    NotEnoughHistory,
    Outcome,
    PastProject,
    chance_of_reaching_operation,
)

Conn = psycopg.Connection[tuple[object, ...]]

DAYS_PER_YEAR = 365.25
OUTCOMES = {"Operational": Outcome.BUILT, "Withdrawn": Outcome.WITHDRAWN, "Active": Outcome.WAITING}

# Enough history to rely on (decision #40): past projects that reached an outcome, and of
# those, how many were built.
MIN_RESOLVED = 30
MIN_BUILT = 10


class ProjectType(StrEnum):
    """The five project types a comparison group can be narrowed to (decision #40). Every
    other mix (geothermal, hydro, wind + battery, ...) only counts in "All projects"."""

    SOLAR = "Solar only"
    SOLAR_BATTERY = "Solar + battery"
    BATTERY = "Battery only"
    WIND = "Wind"
    GAS = "Gas"


# A project's type, from the exact set of its parts as the operator lists them.
TYPE_OF_PARTS: dict[frozenset[str], ProjectType] = {
    frozenset({"Solar"}): ProjectType.SOLAR,
    frozenset({"Solar", "Battery"}): ProjectType.SOLAR_BATTERY,
    frozenset({"Battery"}): ProjectType.BATTERY,
    frozenset({"Wind Turbine"}): ProjectType.WIND,
    frozenset({"Natural Gas"}): ProjectType.GAS,
}


@dataclass(frozen=True)
class SizeBand:
    """MW to grid, from ``low`` up to but not including ``high``."""

    low: float
    high: float | None
    label: str

    def holds(self, mw: float | None) -> bool:
        return mw is not None and self.low <= mw and (self.high is None or mw < self.high)


SIZE_BANDS = (
    SizeBand(0, 50, "under 50 MW"),
    SizeBand(50, 150, "50-150 MW"),
    SizeBand(150, 300, "150-300 MW"),
    SizeBand(300, None, "300 MW and over"),
)


class AreaKind(StrEnum):
    VOLTAGE_SECTION = "voltage section"
    SITE = "site"
    BOTTLENECK_AREA = "bottleneck area"
    COUNTY = "county"
    CALIFORNIA = "California"


@dataclass(frozen=True)
class Level:
    """One comparison group on the ladder from most specific to all projects."""

    description: str
    project_type: ProjectType | None
    size: SizeBand | None
    area_kind: AreaKind
    area: str | None  # the place, site, bottleneck or county; None for California
    projects: int
    resolved: int  # built or withdrawn
    built: int
    enough: bool
    longest_watched_years: float  # the furthest out this group can give a figure for
    native_ids: frozenset[str]


@dataclass(frozen=True)
class Odds:
    used: Level
    ladder: tuple[Level, ...]  # most specific first; ``used`` is the first with enough
    chance: Chance


@dataclass(frozen=True)
class Record:
    """A past project, with what the comparison groups are chosen by."""

    past: PastProject
    project_type: ProjectType | None
    mw: float | None
    places: frozenset[str]


def data_as_of(conn: Conn) -> datetime.date:
    row = conn.execute("SELECT as_of FROM data_as_of WHERE source = 'caiso_raw'").fetchone()
    if row is None or not isinstance(row[0], datetime.date):
        raise LookupError("No date for CAISO's data: load it first (load_all).")
    return row[0]


def history(conn: Conn, as_of: datetime.date | None = None) -> list[Record]:
    """Every old-rules project, with how long it was watched, how it ended, and where.

    ``as_of`` replays the history as it stood on an earlier day, for the backtest: only
    projects that had joined by then, and only outcomes that had happened by then; the rest
    were still waiting. By default, the day the data was taken.
    """
    taken = data_as_of(conn)
    as_of = as_of or taken
    rows = conn.execute(
        "SELECT p.native_id, p.status, p.q_date, p.outcome_date, p.outcome_date_estimated, "
        "  p.mw_to_grid, "
        "  ARRAY(SELECT r.type FROM project_resources r "
        "        WHERE r.source = p.source AND r.native_id = p.native_id), "
        "  ARRAY(SELECT pp.place FROM project_places pp "
        "        WHERE pp.source = p.source AND pp.native_id = p.native_id) "
        "FROM caiso_projects p WHERE p.batch IS DISTINCT FROM 'C15' AND p.q_date IS NOT NULL "
        "ORDER BY p.native_id"
    ).fetchall()
    records = []
    for native_id, status, q_date, outcome_date, estimated, mw, parts, places in rows:
        outcome = OUTCOMES[str(status)]
        assert isinstance(q_date, datetime.date)
        assert isinstance(parts, list) and isinstance(places, list)
        if q_date > as_of:
            continue
        if outcome is Outcome.WAITING:
            end = as_of
        elif not isinstance(outcome_date, datetime.date):
            continue  # an outcome with no date at all: reported by the load
        elif outcome_date > as_of:
            outcome, end = Outcome.WAITING, as_of  # it hadn't happened yet, as of that day
        else:
            end = outcome_date
        # Three outcome dates fall before the queue date in the operator's own file
        # (decision #38); they count as a wait of zero.
        years = max(0, (end - q_date).days) / DAYS_PER_YEAR
        records.append(
            Record(
                PastProject(str(native_id), years, outcome, bool(estimated)),
                TYPE_OF_PARTS.get(frozenset(str(t) for t in parts)),
                float(mw) if isinstance(mw, (int, float)) else None,
                frozenset(str(p) for p in places),
            )
        )
    return records


@dataclass(frozen=True)
class _Area:
    kind: AreaKind
    name: str | None
    description: str
    places: frozenset[str] | None  # None: everywhere


def _areas(conn: Conn, place: str) -> list[_Area]:
    """The place, then wider and wider areas around it, out to California."""
    found = conn.execute("SELECT site, county FROM places WHERE place = %s", (place,)).fetchone()
    if found is None:
        raise LookupError(f"No place called {place!r}.")
    site, county = (str(v) if v is not None else None for v in found)

    def places_where(sql: str, value: object) -> frozenset[str]:
        return frozenset(str(r[0]) for r in conn.execute(sql, (value,)).fetchall())

    areas = [
        _Area(AreaKind.VOLTAGE_SECTION, place, f"at {place}", frozenset({place})),
        _Area(
            AreaKind.SITE,
            site,
            f"at the {site} substation",
            places_where("SELECT place FROM places WHERE site = %s", site),
        ),
    ]
    behind: dict[str, frozenset[str]] = {}
    for (bottleneck,) in conn.execute(
        "SELECT bottleneck FROM place_bottlenecks WHERE place = %s", (place,)
    ).fetchall():
        behind[str(bottleneck)] = places_where(
            "SELECT place FROM place_bottlenecks WHERE bottleneck = %s", bottleneck
        )
    for bottleneck in sorted(behind, key=lambda b: (len(behind[b]), b)):
        areas.append(
            _Area(
                AreaKind.BOTTLENECK_AREA,
                bottleneck,
                f"behind the {bottleneck} bottleneck",
                behind[bottleneck],
            )
        )
    if county:
        areas.append(
            _Area(
                AreaKind.COUNTY,
                county,
                f"in {county} County",
                places_where("SELECT place FROM places WHERE county = %s", county),
            )
        )
    return areas


_CALIFORNIA = _Area(AreaKind.CALIFORNIA, None, "across California", None)


def _level(
    records: list[Record],
    project_type: ProjectType | None,
    size: SizeBand | None,
    area: _Area,
) -> Level:
    members = [
        r
        for r in records
        if (project_type is None or r.project_type is project_type)
        and (size is None or size.holds(r.mw))
        and (area.places is None or r.places & area.places)
    ]
    resolved = sum(r.past.outcome is not Outcome.WAITING for r in members)
    built = sum(r.past.outcome is Outcome.BUILT for r in members)
    group = ", ".join(
        [str(project_type) if project_type else "All projects"] + ([size.label] if size else [])
    )
    return Level(
        description=f"{group}, {area.description}",
        project_type=project_type,
        size=size,
        area_kind=area.kind,
        area=area.name,
        projects=len(members),
        resolved=resolved,
        built=built,
        enough=resolved >= MIN_RESOLVED and built >= MIN_BUILT,
        longest_watched_years=max((r.past.years for r in members), default=0.0),
        native_ids=frozenset(r.past.native_id for r in members),
    )


def comparison_ladder(
    records: list[Record],
    conn: Conn,
    project_type: ProjectType | None,
    mw: float | None,
    place: str | None,
) -> tuple[Level, ...]:
    """Every comparison group for a project, most specific first, with its counts."""
    if mw is not None and project_type is None:
        raise ValueError("A size narrows a project type; give the type too.")
    size = next((band for band in SIZE_BANDS if band.holds(mw)), None)
    groups: list[tuple[ProjectType | None, SizeBand | None]] = []
    if project_type is not None:
        if size is not None:
            groups.append((project_type, size))
        groups.append((project_type, None))
    groups.append((None, None))
    local = _areas(conn, place) if place else []
    pairs = [(groups[0], area) for area in local] + [(g, _CALIFORNIA) for g in groups]
    return tuple(_level(records, kind, size, area) for (kind, size), area in pairs)


def usable_levels(ladder: tuple[Level, ...]) -> list[Level]:
    """The levels a figure may come from, in order: the most specific with enough history,
    then the wider ones that also have enough, but only of the same project type."""
    first = next(level for level in ladder if level.enough or level is ladder[-1])
    return [first] + [
        level
        for level in ladder[ladder.index(first) + 1 :]
        if level.enough and level.project_type is first.project_type
    ]


def odds_for(
    conn: Conn,
    *,
    within_years: float,
    project_type: ProjectType | None = None,
    mw: float | None = None,
    place: str | None = None,
) -> Odds:
    """The chance of being built within ``within_years``, and the typical wait, for the most
    specific comparison group with enough history. ``mw`` is the MW to grid; ``place`` a
    voltage section such as "Birds Landing 230 kV".

    Raises :class:`NotEnoughHistory` if no group of this project type has been watched for
    ``within_years``.
    """
    records = history(conn)
    ladder = comparison_ladder(records, conn, project_type, mw, place)
    usable = usable_levels(ladder)
    used = next((lv for lv in usable if lv.longest_watched_years >= within_years), None)
    if used is None:
        raise NotEnoughHistory(
            f"No figure for {within_years:g} years: no {usable[0].description.split(',')[0]} "
            f"group has been watched that long (longest: "
            f"{max(lv.longest_watched_years for lv in usable):.1f} years)."
        )
    group = [r.past for r in records if r.past.native_id in used.native_ids]
    return Odds(used, ladder, chance_of_reaching_operation(group, within_years))
