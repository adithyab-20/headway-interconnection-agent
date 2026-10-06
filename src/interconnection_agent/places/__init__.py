"""Places: where each project connects, where that is on the map, and what's around it.

A place is one voltage section of a substation site ("Birds Landing 230 kV"). Everything
here is applied through reviewed tables in this folder, by exact match only:

  * ``spellings.csv``       - each spelling of a connection point (tidied by
                              :func:`normalize_station`) -> a site and voltage, or for a
                              project on a line, the line's two end sites.
  * ``positions.csv``       - each site -> its OpenStreetMap substation and coordinates.
  * ``bottleneck_names.csv``- each bottleneck as the bottleneck list names it -> the name
                              the cost file uses, and a short name.
  * ``upgrade_places.csv``  - each planned upgrade -> the places it's at.

Anything these tables don't recognise is left unplaced and reported, never guessed. A site
with no reviewed position falls back to its county.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import psycopg

from interconnection_agent.places.sources import Sources, load_sources
from interconnection_agent.poi import normalize_station

__all__ = ["Sources", "apply_places", "load_sources", "place_id", "voltage_class"]

Conn = psycopg.Connection[tuple[object, ...]]
TABLES = Path(__file__).parent


def voltage_class(kv: int | None) -> int | None:
    """220 kV and 230 kV are the same class, labelled differently by different utilities."""
    return 230 if kv == 220 else kv


def place_id(site: str, kv: int | None) -> str:
    return f"{site} {kv} kV" if kv else site


@dataclass(frozen=True)
class Spelling:
    kind: str  # "substation" or "line"
    site: str
    voltage_kv: int | None
    other_end: str | None  # lines only


def _rows(name: str) -> list[dict[str, str]]:
    path = TABLES / name
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _int(text: str) -> int | None:
    return int(text) if text.strip() else None


def _spellings() -> dict[str, Spelling]:
    """The reviewed spellings. A spelling listed twice with different answers is refused."""
    table: dict[str, Spelling] = {}
    for r in _rows("spellings.csv"):
        spelling = Spelling(
            r["kind"], r["site"], voltage_class(_int(r["voltage_kv"])), r["other_end_site"] or None
        )
        if table.get(r["station_key"], spelling) != spelling:
            raise ValueError(f"spellings.csv: conflicting entries for {r['station_key']!r}")
        table[r["station_key"]] = spelling
    return table


def apply_places(conn: Conn, sources: Sources) -> dict[str, list[str]]:
    """Rebuild places and their links from the reviewed tables.

    Returns what the reviewed tables didn't recognise, by kind: project spellings with no
    place, bottleneck-list points with no place, and upgrade links to places not loaded.
    """
    for table in (
        "upgrade_places",
        "upgrades",
        "place_bottleneck_links",
        "bottlenecks",
        "project_places",
        "places",
    ):
        conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table names

    spellings = _spellings()
    projects = conn.execute(
        "SELECT native_id, raw_poi, county, state FROM projects WHERE source = 'caiso_raw'"
    ).fetchall()

    links: list[tuple[str, str, str]] = []  # (native_id, place, role)
    counties: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    sites: dict[str, tuple[str, int | None]] = {}
    unplaced: set[str] = set()
    for native_id, raw_poi, county, state in projects:
        spelling = spellings.get(normalize_station(str(raw_poi) if raw_poi else None))
        if spelling is None:
            if raw_poi:
                unplaced.add(str(raw_poi))
            continue
        ends = [spelling.site] + ([spelling.other_end] if spelling.other_end else [])
        role = "line_end" if spelling.kind == "line" else "at"
        for site in ends:
            place = place_id(site, spelling.voltage_kv)
            sites[place] = (site, spelling.voltage_kv)
            links.append((str(native_id), place, role))
            if county:
                counties[place][(_county(str(county)), str(state or ""))] += 1

    positions = {r["site"]: r for r in _rows("positions.csv")}
    for place, (site, kv) in sites.items():
        (county, state), _ = (counties[place].most_common(1) or [(("", ""), 0)])[0]
        pos = positions.get(site)
        conn.execute(
            "INSERT INTO places (place, site, voltage_kv, county, state, latitude, longitude, "
            "positioned_by, osm_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                place,
                site,
                kv,
                county or None,
                state or None,
                float(pos["latitude"]) if pos else None,
                float(pos["longitude"]) if pos else None,
                "openstreetmap" if pos else "county",
                pos["osm_id"] if pos else None,
            ),
        )
    for native_id, place, role in links:
        conn.execute(
            "INSERT INTO project_places (source, native_id, place, role) "
            "VALUES ('caiso_raw', %s, %s, %s) ON CONFLICT DO NOTHING",
            (native_id, place, role),
        )

    return {
        "substation spelling": sorted(unplaced),
        "bottleneck-list point": _apply_bottlenecks(conn, sources, spellings, set(sites)),
        "upgrade link": _apply_upgrades(conn, sources, set(sites)),
    }


def _county(text: str) -> str:
    """ "MERCED", "Merced County" -> "Merced"."""
    text = text.strip()
    if text.lower().endswith(" county"):
        text = text[: -len(" county")]
    return text.title()


def _apply_bottlenecks(
    conn: Conn, sources: Sources, spellings: dict[str, Spelling], places: set[str]
) -> list[str]:
    names = {r["bottleneck_list_name"]: r for r in _rows("bottleneck_names.csv")}
    for listed, row in names.items():
        added, cost = sources.cost_to_add_room.get(row["cost_file_name"], (None, None))
        conn.execute(
            "INSERT INTO bottlenecks (bottleneck, room_left_mw, added_mw, cost_musd_2022, "
            "costed_in) VALUES (%s, %s, %s, %s, %s)",
            (
                row["bottleneck"],
                sources.room_left_mw.get(listed),
                added,
                cost,
                "CAISO transmission capability estimates, 2026" if cost is not None else None,
            ),
        )
    unmatched = []
    for point, listed_names in sources.behind.items():
        spelling = spellings.get(normalize_station(point))
        if spelling is None or spelling.kind != "substation":
            unmatched.append(point)
            continue
        place = place_id(spelling.site, spelling.voltage_kv)
        if place not in places:
            continue
        for listed in listed_names:
            if listed in names:
                conn.execute(
                    "INSERT INTO place_bottleneck_links (place, bottleneck) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (place, names[listed]["bottleneck"]),
                )
    return sorted(unmatched)


UPGRADE_SOURCE = "CAISO approved-projects tracker, July 2026"
FACT_SHEETS = "CAISO 2025-2026 transmission plan, Appendix H"


def _apply_upgrades(conn: Conn, sources: Sources, places: set[str]) -> list[str]:
    for u in sources.upgrades:
        conn.execute(
            "INSERT INTO upgrades (plan_id, name, utility, expected_finish, expected_finish_year, "
            "cost_low_musd, cost_high_musd, source, fact_sheet_page) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (plan_id) DO NOTHING",
            (
                u.plan_id,
                u.name,
                u.utility,
                u.expected_finish,
                u.expected_finish_year,
                u.cost_low_musd,
                u.cost_high_musd,
                UPGRADE_SOURCE + (f"; {FACT_SHEETS}" if u.fact_sheet_page else ""),
                u.fact_sheet_page,
            ),
        )
    unmatched = []
    for r in _rows("upgrade_places.csv"):
        place = place_id(r["site"], voltage_class(_int(r["voltage_kv"])))
        if place not in places:
            unmatched.append(f"{r['plan_id']} at {place}")
            continue
        conn.execute(
            "INSERT INTO upgrade_places (plan_id, place) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (r["plan_id"], place),
        )
    return sorted(unmatched)
