"""Loading and organising the data: the five behaviours of ticket "Load and organise the data".

One call, ``load_all(data folder, database)``, loads everything. These tests run it once on
the real files in ``data/`` and read the results the way the rest of the product will: through
the database views and the load report. Expected values come from the spreadsheets themselves,
never from the code under test.
"""

from __future__ import annotations

import datetime
import statistics
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import openpyxl
import psycopg
import pytest

from interconnection_agent.db import connect
from interconnection_agent.load import LoadReport, load_all

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
    assert placeless == set(report.unrecognised["substation spelling"])

    # Study-progress values outside the reviewed mapping (the main report has an "Unexpected"
    # and a "Withdrawn" in its study columns) leave furthest_step empty and are reported.
    assert {"Unexpected", "Withdrawn"} <= set(report.unrecognised["study progress"])
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

    # Trout Canyon isn't in OpenStreetMap: it falls back to its county, with no point.
    assert one(
        conn,
        "SELECT positioned_by, county, latitude FROM places WHERE site = 'Trout Canyon'",
    ) == ("county", "Clark", None)

    placed, waiting = one(
        conn,
        "SELECT sum(r.mw) FILTER (WHERE EXISTS (SELECT 1 FROM project_places pp JOIN places pl "
        "  USING (place) WHERE pp.source = p.source AND pp.native_id = p.native_id "
        "  AND pl.positioned_by = 'openstreetmap')), sum(r.mw) "
        "FROM caiso_projects p JOIN project_resources r USING (source, native_id) "
        "WHERE p.status = 'Active'",
    )
    assert report.share_of_waiting_mw_placed == pytest.approx(num(placed) / num(waiting))
    assert 0.5 < report.share_of_waiting_mw_placed < 0.85


def test_planned_upgrades_and_cost_to_add_room_are_attached_to_substations(
    loaded: tuple[Conn, LoadReport],
) -> None:
    conn, _ = loaded

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
