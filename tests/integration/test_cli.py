"""Listing projects from the command line, by county or by substation."""

from __future__ import annotations

from pathlib import Path

import psycopg

from interconnection_agent.cli import list_active_projects, list_projects_at_poi
from interconnection_agent.ingest import run_caiso_ingest

Conn = psycopg.Connection[tuple[object, ...]]
WORKBOOK = Path(__file__).resolve().parents[2] / "data" / "publicqueuereport.xlsx"


def test_county_listing_ignores_case_and_never_shows_the_other_dataset(conn: Conn) -> None:
    run_caiso_ingest(WORKBOOK, conn)
    conn.execute(
        "INSERT INTO projects (source, native_id, status, county, iso) "
        "VALUES ('lbnl', 'LBNL-SOLANO-1', 'Active', 'SOLANO', 'CAISO')"
    )
    projects = list_active_projects(conn, "Solano")
    ids = {p.native_id for p in projects}
    assert "CAISO-0022" in ids  # Montezuma is in Solano County
    assert "LBNL-SOLANO-1" not in ids
    assert list_active_projects(conn, "NOWHERE") == []


def test_substation_listing_groups_spellings_and_ignores_case(conn: Conn) -> None:
    run_caiso_ingest(WORKBOOK, conn)
    # Eldorado 230 kV is written three ways in the file; one query returns all of them.
    eldorado = list_projects_at_poi(conn, "eldorado substation 230 kV")
    assert len({p.raw_poi for p in eldorado}) > 1
    assert list_projects_at_poi(conn, "Nonexistent Substation 999 kV") == []
