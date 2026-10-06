"""Reader for CAISO's separate report on the 2023 batch (the first under the new rules).

CAISO lists this batch in its own workbook (``cluster-15-interconnection-requests.xlsx``):
one sheet of projects still in the queue and one of projects that withdrew. They land in
the same ``projects`` table as the main report, tagged ``batch = 'C15'``, so they count as
competition everywhere. The analysis keeps their outcomes out of the old-rules history.

This report names fuels and service types differently from the main report; the two
tables below translate them to the main report's words. A value not listed is reported,
never guessed.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import psycopg

from interconnection_agent.ingest import _cells
from interconnection_agent.poi import load_alias_table

BATCH = "C15"

# Sheet name (CAISO's own, trailing space included) -> canonical status.
SHEETS = {"Cluster 15 ": "Active", "Withdrawn": "Withdrawn"}

FUELS: dict[str, str] = {
    "Storage/Battery": "Battery",
    "Photovoltaic/Solar": "Solar",
    "Storage/Solar": "Solar",
    "Wind Turbine/Wind": "Wind Turbine",
    "Combustion Turbine/Hydrogen": "Hydrogen",
    "Storage/Compressed Air": "Compressed Air",
    "Hydro/Pumped-Storage Hydro": "Pumped-Storage hydro",
    "Biomass/Biofuel": "Biofuel",
}

DELIVERABILITY: dict[str, str] = {
    "Full Capacity Deliverability Status Requested": "Full Capacity",
    "Merchant- Full Capacity Deliverability Status Requested": "Full Capacity",
    "Energy Only Requested": "Energy Only",
}

_UPSERT = """
    INSERT INTO projects (
        source, native_id, status, q_date, proposed_online_date, withdrawn_date, county,
        state, iso, raw_poi, normalized_poi, poi_unmapped, utility, batch, deliverability,
        mw_to_grid
    ) VALUES (
        'caiso_raw', %(native_id)s, %(status)s, %(q_date)s, %(proposed_online_date)s,
        %(withdrawn_date)s, %(county)s, %(state)s, 'CAISO', %(raw_poi)s, %(normalized_poi)s,
        %(poi_unmapped)s, %(utility)s, %(batch)s, %(deliverability)s, %(mw_to_grid)s
    )
    ON CONFLICT (source, native_id) DO UPDATE SET
        status = EXCLUDED.status, q_date = EXCLUDED.q_date,
        proposed_online_date = EXCLUDED.proposed_online_date,
        withdrawn_date = EXCLUDED.withdrawn_date, county = EXCLUDED.county,
        state = EXCLUDED.state, raw_poi = EXCLUDED.raw_poi,
        normalized_poi = EXCLUDED.normalized_poi, poi_unmapped = EXCLUDED.poi_unmapped,
        utility = EXCLUDED.utility,
        batch = EXCLUDED.batch, deliverability = EXCLUDED.deliverability,
        mw_to_grid = EXCLUDED.mw_to_grid
"""

_UPSERT_RESOURCE = """
    INSERT INTO project_resources (source, native_id, type, mw)
    VALUES ('caiso_raw', %(native_id)s, %(type)s, %(mw)s)
    ON CONFLICT (source, native_id, type) DO UPDATE SET mw = EXCLUDED.mw
"""


def run_caiso_2023_ingest(
    workbook_path: Path, conn: psycopg.Connection[tuple[object, ...]]
) -> list[str]:
    """Load the 2023-batch report; return the fuel or service-type values it didn't know."""
    unknown: set[str] = set()
    aliases = load_alias_table()
    workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        for sheet_name, status in SHEETS.items():
            rows = workbook[sheet_name].iter_rows(values_only=True)
            header = [_cells.clean(h) or "" for h in next(rows)]
            for row in rows:
                cells = dict(zip(header, row, strict=False))
                if cells.get("Queue Number") is None:
                    continue
                native_id = f"CAISO-{int(str(cells['Queue Number'])):04d}"
                service = _cells.clean(cells.get("Service Type")) or ""
                raw_poi = _cells.verbatim(cells.get("POI"))
                normalized_poi = aliases.resolve(raw_poi)
                if service not in DELIVERABILITY:
                    unknown.add(service)
                conn.execute(
                    _UPSERT,
                    {
                        "native_id": native_id,
                        "status": status,
                        "q_date": _cells.as_date(cells.get("Queue Date")),
                        "proposed_online_date": _cells.as_date(cells.get("Requested COD")),
                        "withdrawn_date": _cells.as_date(cells.get("Withdrawal Date")),
                        "county": _cells.clean(cells.get("PROJECT COUNTY")),
                        "state": _cells.clean(cells.get("Project State")),
                        "raw_poi": raw_poi,
                        "normalized_poi": normalized_poi,
                        "poi_unmapped": normalized_poi is None,
                        "utility": _cells.clean(cells.get("PTO")),
                        "batch": BATCH,
                        "deliverability": DELIVERABILITY.get(service),
                        "mw_to_grid": _cells.mw_or_none(cells.get("NET MW POI")),
                    },
                )
                by_fuel: dict[str, float] = {}
                for n in (1, 2, 3):
                    raw_fuel = _cells.clean(cells.get(f"Generation/Fuel {n}"))
                    if raw_fuel in (None, "N/A"):
                        continue
                    if raw_fuel not in FUELS:
                        unknown.add(raw_fuel)
                        continue
                    fuel = FUELS[raw_fuel]
                    by_fuel[fuel] = by_fuel.get(fuel, 0.0) + (
                        _cells.mw_or_none(cells.get(f"NET MW {n}")) or 0.0
                    )
                for fuel, mw in by_fuel.items():
                    conn.execute(_UPSERT_RESOURCE, {"native_id": native_id, "type": fuel, "mw": mw})
    finally:
        workbook.close()
    return sorted(unknown)
