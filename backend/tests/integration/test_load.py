"""Loading and organising the data: the five behaviours of ticket "Load and organise the data".

One call, ``load_all(data folder, database)``, loads everything. These tests run it once on
the real files in ``data/`` and read the results the way the rest of the product will: through
the database views and the load report. Expected values come from the spreadsheets themselves,
never from the code under test.
"""

from __future__ import annotations

import csv
import datetime
import functools
import json
import math
import re
import statistics
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import openpyxl
import psycopg
import pytest

from interconnection_agent.db import connect
from interconnection_agent.load import LoadReport, load_all
from interconnection_agent.poi import normalize_station
from interconnection_agent.unrecognised import Unrecognised

Conn = psycopg.Connection[tuple[object, ...]]
DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def loaded() -> Iterator[tuple[Conn, LoadReport]]:
    """Load everything once for this module; roll it all back afterwards."""
    with connect() as conn:
        conn.autocommit = False
        try:
            yield conn, load_all(DATA, conn)
        finally:
            conn.rollback()


def num(value: object) -> float:
    assert isinstance(value, (int, float, Decimal)), value
    return float(value)


def one(conn: Conn, sql: str, *params: object) -> tuple[object, ...]:
    row = conn.execute(sql, params).fetchone()
    assert row is not None, sql
    return row


def places_of(conn: Conn, native_id: str) -> set[tuple[object, ...]]:
    return set(
        conn.execute(
            "SELECT pl.site, pl.voltage_kv, pp.role FROM project_places pp "
            "JOIN places pl USING (place) WHERE pp.source = 'caiso_raw' AND pp.native_id = %s",
            (native_id,),
        ).fetchall()
    )


def _km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    rad = math.pi / 180
    x = (lon_b - lon_a) * rad * math.cos((lat_a + lat_b) / 2 * rad)
    return 6371 * math.hypot(x, (lat_b - lat_a) * rad)


@functools.cache
def _osm_points() -> dict[str, tuple[float, float]]:
    elements = json.loads((DATA / "osm_substations_ca_nv_az.json").read_text())["elements"]
    middles = [(f"{e['type']}/{e['id']}", e.get("center") or e) for e in elements]
    return {osm_id: (m["lat"], m["lon"]) for osm_id, m in middles}


def _cites_its_dataset(positioned_by: str, source: str, lat: float, lon: float) -> bool:
    """A point is traceable when the OpenStreetMap shape it names is in the committed copy,
    at the same spot. A point read off a document can only name the document."""
    shape = re.search(r"(node|way|relation)/\d+", source)
    if positioned_by == "openstreetmap":
        point = _osm_points().get(shape.group(0)) if shape else None
    elif positioned_by in ("document", "planned"):
        # A document names the place in words; where it also pins down a shape on the map,
        # the point has to be that shape.
        point = _osm_points().get(shape.group(0)) if shape else (lat, lon)
        return len(source) > 20 and point is not None and _km(lat, lon, *point) < 1
    else:
        return False
    return point is not None and _km(lat, lon, *point) < 1


def _waiting_mw_and_connection_points() -> list[tuple[float, str]]:
    """(MW to grid, connection point as written) for every waiting project in both reports."""
    waiting = []
    main = openpyxl.load_workbook(DATA / "publicqueuereport.xlsx", read_only=True)
    rows = list(main["Grid GenerationQueue"].iter_rows(min_row=4, values_only=True))
    header = [" ".join(str(c).split()) if c else "" for c in rows[0]]
    mw, poi = header.index("Net MWs to Grid"), header.index("Station or Transmission Line")
    waiting += [(num(r[mw]), str(r[poi])) for r in rows[1:] if isinstance(r[mw], (int, float))]
    batch = openpyxl.load_workbook(
        DATA / "cluster-15-interconnection-requests.xlsx", read_only=True
    )
    rows = list(batch["Cluster 15 "].iter_rows(values_only=True))
    mw, poi = rows[0].index("NET MW POI"), rows[0].index("POI")
    waiting += [(num(r[mw]), str(r[poi])) for r in rows[1:] if isinstance(r[mw], (int, float))]
    return waiting


def _share_placed_from_the_files() -> float:
    places = Path(__file__).resolve().parents[2] / "src/interconnection_agent/places"
    with (places / "spellings.csv").open(newline="") as f:
        ends = {r["poi_key"]: {r["site"], r["other_end_site"]} - {""} for r in csv.DictReader(f)}
    with (places / "positions.csv").open(newline="") as f:
        positioned = {r["site"] for r in csv.DictReader(f) if r["positioned_by"] != "county"}
    waiting = _waiting_mw_and_connection_points()
    placed = sum(mw for mw, poi in waiting if ends.get(normalize_station(poi), set()) & positioned)
    return placed / sum(mw for mw, _ in waiting)


def test_loading_gives_every_project_its_facts_and_place_and_reloading_changes_nothing(
    loaded: tuple[Conn, LoadReport],
) -> None:
    conn, _ = loaded

    # Every project from both CAISO reports: the main report (270 waiting, 249 built,
    # 1,759 withdrawn) and the separate 2023-batch report (86 waiting, 84 withdrawn).
    counts = {
        (batch_2023, status): n
        for batch_2023, status, n in conn.execute(
            "SELECT batch IS NOT DISTINCT FROM 'C15', status, count(*) FROM caiso_projects "
            "GROUP BY 1, 2"
        ).fetchall()
    }
    assert counts == {
        (False, "Active"): 270,
        (False, "Operational"): 249,
        (False, "Withdrawn"): 1759,
        (True, "Active"): 86,
        (True, "Withdrawn"): 84,
    }

    # Montezuma (queue 22), read off the main report: wind + battery, 38 MW each, signed
    # agreement, partial capacity, connects at Birds Landing 230 kV.
    assert one(
        conn,
        "SELECT status, batch, furthest_step, deliverability, q_date "
        "FROM caiso_projects WHERE native_id = 'CAISO-0022'",
    ) == ("Active", "AMEND 39", "Agreement signed", "Partial Capacity", datetime.date(2003, 11, 18))
    assert set(
        conn.execute(
            "SELECT type, mw FROM project_resources WHERE source = 'caiso_raw' "
            "AND native_id = 'CAISO-0022'"
        ).fetchall()
    ) == {("Battery", 38.0), ("Wind Turbine", 38.0)}
    assert places_of(conn, "CAISO-0022") == {("Birds Landing", 230, "at")}

    # Annapurna (queue 2244), from the 2023-batch report: a waiting battery at Quinto 230 kV.
    assert one(
        conn, "SELECT status, batch, q_date FROM caiso_projects WHERE native_id = 'CAISO-2244'"
    ) == ("Active", "C15", datetime.date(2025, 2, 12))
    assert places_of(conn, "CAISO-2244") == {("Quinto", 230, "at")}

    # Queue 61 connects partway along the Helm-Kerman 70 kV line: it counts at both ends.
    assert places_of(conn, "CAISO-0061") == {("Helm", 70, "line_end"), ("Kerman", 70, "line_end")}

    # Loading again changes nothing.
    before = conn.execute("SELECT count(*) FROM projects").fetchone()
    snapshot = conn.execute(
        "SELECT * FROM caiso_projects WHERE native_id IN ('CAISO-0022', 'CAISO-2244') ORDER BY 1, 2"
    ).fetchall()
    load_all(DATA, conn)
    assert conn.execute("SELECT count(*) FROM projects").fetchone() == before
    assert (
        conn.execute(
            "SELECT * FROM caiso_projects WHERE native_id IN ('CAISO-0022', 'CAISO-2244') "
            "ORDER BY 1, 2"
        ).fetchall()
        == snapshot
    )


def test_values_the_reviewed_tables_dont_know_are_reported_never_guessed(
    loaded: tuple[Conn, LoadReport],
) -> None:
    conn, report = loaded

    # Every project left without a place is in the report, and every reported one has none.
    placeless = {
        r[0]
        for r in conn.execute(
            "SELECT raw_poi FROM caiso_projects p WHERE NOT EXISTS ("
            "  SELECT 1 FROM project_places pp"
            "  WHERE pp.source = p.source AND pp.native_id = p.native_id)"
        ).fetchall()
    }
    assert placeless == set(report.unrecognised[Unrecognised.SUBSTATION_SPELLING])

    # Study-progress values outside the reviewed mapping (the main report has an "Unexpected"
    # and a "Withdrawn" in its study columns) leave furthest_step empty and are reported.
    assert {"Unexpected", "Withdrawn"} <= set(report.unrecognised[Unrecognised.STUDY_PROGRESS])
    unknown_progress = one(
        conn,
        "SELECT count(*) FROM caiso_projects "
        "WHERE furthest_step IS NULL AND batch IS DISTINCT FROM 'C15'",
    )[0]
    assert unknown_progress == report.projects_with_unrecognised_study_progress


def test_a_project_missing_its_outcome_date_gets_a_clearly_marked_estimate(
    loaded: tuple[Conn, LoadReport],
) -> None:
    conn, report = loaded

    # Built project with a real date: used as-is.
    assert one(
        conn,
        "SELECT outcome_date, outcome_date_estimated FROM caiso_projects "
        "WHERE native_id = 'CAISO-1A'",
    ) == (datetime.date(2009, 10, 2), False)

    # Built project with no online date (Red Bluff, queue 146): its proposed date, marked.
    assert one(
        conn,
        "SELECT actual_online_date, outcome_date, outcome_date_estimated "
        "FROM caiso_projects WHERE native_id = 'CAISO-0146'",
    ) == (None, datetime.date(2008, 12, 1), True)

    # Withdrawn project with no withdrawal date (Encina, queue 5, joined 2000): the typical
    # wait to withdraw for projects that joined the same year, marked. Worked out here
    # straight from the spreadsheet.
    sheet = openpyxl.load_workbook(DATA / "publicqueuereport.xlsx", read_only=True)[
        "Withdrawn Generation Projects"
    ]
    rows = list(sheet.iter_rows(min_row=4, values_only=True))
    header = [" ".join(str(c).split()) if c else "" for c in rows[0]]
    q, w = header.index("Queue Date"), header.index("Withdrawn Date")
    waits = []
    for r in rows[1:]:
        queued, withdrawn = r[q], r[w]
        if isinstance(queued, datetime.datetime) and isinstance(withdrawn, datetime.datetime):
            if queued.year == 2000 and withdrawn >= queued:
                waits.append((withdrawn.date() - queued.date()).days)
    expected = datetime.date(2000, 8, 9) + datetime.timedelta(days=round(statistics.median(waits)))
    assert one(
        conn,
        "SELECT withdrawn_date, outcome_date, outcome_date_estimated "
        "FROM caiso_projects WHERE native_id = 'CAISO-0005'",
    ) == (None, expected, True)

    assert report.estimated_outcome_dates == 51  # 39 withdrawn + 12 built, per the report file

    # A built project with no online date and no proposed one has nothing to estimate from:
    # it's left without an outcome date and reported. (Today's file has none.)
    undated_built = {
        r[0]
        for r in conn.execute(
            "SELECT native_id FROM caiso_projects WHERE status = 'Operational' "
            "AND outcome_date IS NULL"
        ).fetchall()
    }
    assert undated_built == set(report.built_projects_without_a_date)


def test_each_substation_gets_a_map_position_or_falls_back_to_its_county(
    loaded: tuple[Conn, LoadReport],
) -> None:
    conn, report = loaded

    lat, lon, by, osm_id = one(
        conn,
        "SELECT latitude, longitude, positioned_by, osm_id FROM places "
        "WHERE site = 'Birds Landing' AND voltage_kv = 230",
    )
    assert by == "openstreetmap" and osm_id
    assert 37.9 < num(lat) < 38.4 and -122.2 < num(lon) < -121.6  # Solano County

    # Two substations share the name Mesa. The 500 kV one is in Los Angeles County, not at
    # the other Mesa in San Luis Obispo County.
    lat, lon = one(conn, "SELECT latitude, longitude FROM places WHERE place LIKE 'Mesa%%500 kV'")
    assert 33.9 < num(lat) < 34.2 and -118.3 < num(lon) < -118.0

    # Manning 500 kV isn't built yet; the CPUC's filing for it says where it will go, and the
    # point says so. Every point says where it came from.
    lat, lon, by, source = one(
        conn,
        "SELECT latitude, longitude, positioned_by, position_source FROM places "
        "WHERE site = 'Manning' AND voltage_kv = 500",
    )
    assert by == "planned" and "CPUC" in str(source)
    assert 36.5 < num(lat) < 36.7 and -120.7 < num(lon) < -120.5  # Fresno County
    assert one(
        conn,
        "SELECT count(*) FROM places WHERE positioned_by <> 'county' AND position_source IS NULL",
    ) == (0,)

    # Every point traces back to a row in a public dataset committed here, at the same spot.
    untraceable = [
        (site, by, source)
        for site, by, source, lat, lon in conn.execute(
            "SELECT site, positioned_by, position_source, latitude, longitude FROM places "
            "WHERE positioned_by <> 'county'"
        ).fetchall()
        if not _cites_its_dataset(str(by), str(source), num(lat), num(lon))
    ]
    assert untraceable == []

    # No public document says where the proposed Lee Lake substation would go, and nothing is
    # drawn there. Rather than guess, it falls back to its county, with no point.
    assert one(
        conn,
        "SELECT positioned_by, county, latitude FROM places WHERE site = 'Lee Lake'",
    ) == ("county", "Riverside", None)

    # The share of waiting MW whose substation is on the map, worked out here from the two
    # reports' "MW to grid" columns and the reviewed spelling and position tables.
    assert report.share_of_waiting_mw_placed == pytest.approx(_share_placed_from_the_files())
    assert 0.85 < report.share_of_waiting_mw_placed <= 1


def test_a_substation_is_in_the_county_it_stands_in_not_where_its_projects_are(
    loaded: tuple[Conn, LoadReport],
) -> None:
    conn, _ = loaded

    # Projects in Mexico connect at these three, and the operator's file gives the projects'
    # own location. The substations themselves stand in California.
    counties = conn.execute(
        "SELECT DISTINCT site, county, state FROM places "
        "WHERE site IN ('Imperial Valley', 'East County', 'Miguel') ORDER BY site"
    ).fetchall()
    assert counties == [
        ("East County", "San Diego", "CA"),
        ("Imperial Valley", "Imperial", "CA"),
        ("Miguel", "San Diego", "CA"),
    ]
    assert one(conn, "SELECT count(*) FROM places WHERE state = 'MX'") == (0,)


def test_planned_upgrades_and_cost_to_add_room_are_attached_to_substations(
    loaded: tuple[Conn, LoadReport],
) -> None:
    conn, report = loaded

    # Newark 230 kV: the operator's 2025-26 plan approves a transformer upgrade there,
    # finishing May 2032, costing $31.3M-$62.6M, paid by all electricity customers.
    assert one(
        conn,
        "SELECT name, expected_finish, cost_low_musd, cost_high_musd, paid_by "
        "FROM planned_upgrades WHERE plan_id = '2526-R-12'",
    ) == (
        "Newark 230/115 kV Bank Upgrade",
        datetime.date(2032, 5, 1),
        31.3,
        62.6,
        "all electricity customers",
    )
    # The fact sheet spells this one "Tes l a – Trimble – Metcalf ..." (page 13); a reviewed
    # name table still gives the tracker's upgrade its $712M-$1,424M.
    assert one(
        conn,
        "SELECT cost_low_musd, cost_high_musd FROM planned_upgrades WHERE plan_id = '2526-R-17'",
    ) == (712.0, 1424.0)
    assert ("Newark", 230) in set(
        conn.execute(
            "SELECT pl.site, pl.voltage_kv FROM planned_upgrades u JOIN places pl USING (place) "
            "WHERE u.plan_id = '2526-R-12'"
        ).fetchall()
    )

    # Whirlwind 230 kV sits behind the Antelope-Vincent bottleneck, where the next upgrade adds
    # 1,500 MW for $13.2M (2022 dollars): about $8.80 per kW.
    cost = one(
        conn,
        "SELECT b.cost_per_kw_2022 FROM place_bottlenecks b JOIN places pl USING (place) "
        "WHERE pl.site = 'Whirlwind' AND pl.voltage_kv = 230 AND b.bottleneck = 'Antelope-Vincent'",
    )[0]
    assert num(cost) == pytest.approx(13.2e6 / 1_500_000)

    # 22 bottlenecks in the cost file give no added MW or no cost for their next upgrade
    # ("N/A"): GLW has 853 MW but no cost; Mira Loma-Mesa has neither. They get no cost to
    # add room, and are reported.
    uncosted = {v.split(":")[0] for v in report.unrecognised[Unrecognised.BOTTLENECK_COST]}
    assert len(uncosted) == 22
    assert {"GLW 230kV area constraint", "Mira Loma-Mesa Constraint"} <= uncosted
    assert "Antelope-Vincent Constraint" not in uncosted

    # A point on the bottleneck list that's a line counts at both ends, saying which line,
    # unless an end has its own row in the list: the list's own answer for it stands.
    # The Pittsburg-Kirker-Columbia Steel 115 kV line sits behind Collinsville-Tesla.
    line = "Pittsburg-Kirker-Columbia Steel 115 kV line"
    assert set(
        conn.execute(
            "SELECT pl.site, pl.voltage_kv FROM place_bottlenecks b JOIN places pl USING (place) "
            "WHERE b.bottleneck = 'Collinsville-Tesla 500 kV Line' AND b.via_line = %s",
            (line,),
        ).fetchall()
    ) == {("Pittsburg", 115), ("Columbia Steel", 115)}
    # Tesla 230 kV ends the Pittsburg-Tesla line but has its own row: only that row counts.
    own, from_lines = one(
        conn,
        "SELECT count(*) FILTER (WHERE via_line IS NULL), count(*) FILTER (WHERE via_line IS NOT "
        "NULL) FROM place_bottlenecks WHERE place = 'Tesla 230 kV'",
    )
    assert num(own) > 0 and from_lines == 0


@pytest.mark.skipif(
    not (DATA / "LBNL_Ix_Queue_Data_File_thru2025.xlsx").exists(),
    reason="Berkeley Lab file not present (large, not committed)",
)
def test_berkeley_lab_areas_with_no_grid_operator_are_never_stored_as_one(
    loaded: tuple[Conn, LoadReport],
) -> None:
    conn, report = loaded
    assert report.lbnl_loaded
    # "West" and "Southeast" are catch-all areas run by local utilities, not grid operators.
    assert one(
        conn,
        "SELECT count(*) FILTER (WHERE iso IN ('West', 'Southeast')), "
        "count(*) FILTER (WHERE iso IS NULL AND non_iso_entity IS NULL), "
        "count(*) FILTER (WHERE study_region IS NOT NULL) FROM lbnl_projects",
    ) == (0, 0, 0)
