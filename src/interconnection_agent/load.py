"""Load everything the product needs from ``data/``, in one call.

``load_all`` reads both CAISO queue reports, Berkeley Lab's national file (when present: it's
large and not committed), the substation positions, the bottleneck list, the costs to add
room, and the planned upgrades. Places, positions, bottleneck links and upgrade links are
applied through reviewed tables in ``interconnection_agent/places/``: anything those tables
don't recognise is reported in the :class:`LoadReport`, never guessed.

Loading twice changes nothing. The caller owns the transaction.
"""

from __future__ import annotations

import datetime
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from interconnection_agent.ingest import run_caiso_ingest, run_lbnl_ingest
from interconnection_agent.ingest.caiso_2023 import run_caiso_2023_ingest
from interconnection_agent.places import apply_places, load_sources

Conn = psycopg.Connection[tuple[object, ...]]

MAIN_REPORT = "publicqueuereport.xlsx"
BATCH_2023_REPORT = "cluster-15-interconnection-requests.xlsx"
LBNL_FILE = "LBNL_Ix_Queue_Data_File_thru2025.xlsx"


@dataclass(frozen=True)
class LoadReport:
    """What a load did, and everything it couldn't place or recognise."""

    # Kind ("substation spelling", "study progress", "2023-batch value") -> values not
    # recognised by the reviewed tables.
    unrecognised: dict[str, list[str]] = field(default_factory=dict)
    projects_with_unrecognised_study_progress: int = 0
    estimated_outcome_dates: int = 0
    share_of_waiting_mw_placed: float = 0.0
    lbnl_loaded: bool = False


def load_all(data_dir: Path, conn: Conn) -> LoadReport:
    main = run_caiso_ingest(data_dir / MAIN_REPORT, conn)
    unknown_2023 = run_caiso_2023_ingest(data_dir / BATCH_2023_REPORT, conn)
    lbnl_path = data_dir / LBNL_FILE
    if lbnl_path.exists():
        run_lbnl_ingest(lbnl_path, conn)
    estimated = _estimate_missing_outcome_dates(conn)
    sources = load_sources(data_dir)
    unrecognised_places = apply_places(conn, sources)

    study_values = sorted({v for s in main.sheets for v in s.unrecognised_study_values})
    return LoadReport(
        unrecognised={
            **unrecognised_places,
            "study progress": study_values,
            "2023-batch value": unknown_2023,
            "upgrade cost": sources.unread_upgrade_costs,
        },
        projects_with_unrecognised_study_progress=sum(
            s.unrecognised_study_rows for s in main.sheets
        ),
        estimated_outcome_dates=estimated,
        share_of_waiting_mw_placed=_share_of_waiting_mw_placed(conn),
        lbnl_loaded=lbnl_path.exists(),
    )


def _estimate_missing_outcome_dates(conn: Conn) -> int:
    """Give CAISO projects with an outcome but no date an estimated date, and count them.

    Built projects use their proposed online date. Withdrawn projects use the typical
    (median) wait to withdraw among projects that joined the same year, falling back to the
    median over all years. Real date columns are never touched.
    """
    rows = conn.execute(
        "SELECT q_date, withdrawn_date FROM projects WHERE source = 'caiso_raw' "
        "AND status = 'Withdrawn' AND withdrawn_date IS NOT NULL AND q_date IS NOT NULL "
        "AND withdrawn_date >= q_date AND batch IS DISTINCT FROM 'C15'"
    ).fetchall()
    waits_by_year: dict[int, list[int]] = defaultdict(list)
    for q_date, withdrawn in rows:
        assert isinstance(q_date, datetime.date) and isinstance(withdrawn, datetime.date)
        waits_by_year[q_date.year].append((withdrawn - q_date).days)
    all_waits = [w for ws in waits_by_year.values() for w in ws]

    conn.execute("UPDATE projects SET estimated_outcome_date = NULL WHERE source = 'caiso_raw'")
    conn.execute(
        "UPDATE projects SET estimated_outcome_date = proposed_online_date "
        "WHERE source = 'caiso_raw' AND status = 'Operational' AND actual_online_date IS NULL"
    )
    undated = conn.execute(
        "SELECT native_id, q_date FROM projects WHERE source = 'caiso_raw' "
        "AND status = 'Withdrawn' AND withdrawn_date IS NULL AND q_date IS NOT NULL"
    ).fetchall()
    for native_id, q_date in undated:
        assert isinstance(q_date, datetime.date)
        waits = waits_by_year.get(q_date.year) or all_waits
        if not waits:
            continue  # no dated withdrawals at all to estimate from; left undated
        estimate = q_date + datetime.timedelta(days=round(statistics.median(waits)))
        conn.execute(
            "UPDATE projects SET estimated_outcome_date = %s "
            "WHERE source = 'caiso_raw' AND native_id = %s",
            (estimate, native_id),
        )
    count = conn.execute(
        "SELECT count(*) FROM projects WHERE source = 'caiso_raw' "
        "AND estimated_outcome_date IS NOT NULL"
    ).fetchone()
    return int(str(count[0])) if count else 0


def _share_of_waiting_mw_placed(conn: Conn) -> float:
    """Share of the MW waiting in CAISO's queue whose substation has a map position."""
    row = conn.execute(
        "SELECT sum(r.mw) FILTER (WHERE EXISTS (SELECT 1 FROM project_places pp JOIN places pl "
        "  USING (place) WHERE pp.source = p.source AND pp.native_id = p.native_id "
        "  AND pl.positioned_by <> 'county')), sum(r.mw) "
        "FROM caiso_projects p JOIN project_resources r USING (source, native_id) "
        "WHERE p.status = 'Active'"
    ).fetchone()
    if not row or not row[1]:
        return 0.0
    return float(str(row[0] or 0)) / float(str(row[1]))
