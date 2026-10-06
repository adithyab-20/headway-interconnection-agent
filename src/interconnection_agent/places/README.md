# Reviewed place tables

These tables are applied by exact match only. They were drafted by
`scripts/propose_places.py` and reviewed by a person before being committed.

| File | What it maps |
|---|---|
| `spellings.csv` | each spelling of a connection point (tidied) → site and voltage, or a line's two end sites |
| `positions.csv` | each site → its coordinates and what they come from (`positioned_by`, `source`) |
| `bottleneck_names.csv` | each bottleneck in CAISO's 2024 list → its entry in the 2026 cost estimates |
| `upgrade_places.csv` | each planned upgrade → the places it's at |
| `fact_sheet_names.csv` | each upgrade fact sheet the tracker names differently → the tracker's plan id (written by hand) |

Most of `positions.csv` is derived from OpenStreetMap: © OpenStreetMap contributors,
available under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
See https://www.openstreetmap.org/copyright. The few others are read off named public
documents, each cited in its row.

Some rows were later corrected by hand (substations sharing a name, misspelled sites,
descriptions the draft misread). Running `propose_places.py --apply` again would overwrite
them, so re-check its output against these tables first.

## Where a position is allowed to come from

The decision and its reasons: `docs/adr/0004-where-map-points-come-from.md`.

`positioned_by` says which of these answered, and `source` names the row or document, so
every point on the map can be traced back to something public. In order of preference:

| `positioned_by` | Accepted when |
|---|---|
| `openstreetmap` | OpenStreetMap names a substation with this site's name, in the projects' own or a neighbouring county. A namesake further away is flagged for review, not used. |
| `document` | A public document fixes the spot without judgement on our part: coordinates, a parcel, or a named road junction with a distance and direction. Where OpenStreetMap has drawn a substation there, the point is that shape and the document says which one; where it has drawn nothing, the document's own coordinates stand. |
| `planned` | The same, for a substation that isn't built yet. There is nothing on the ground and nothing drawn; the point is where the filing says it will go. |
| `county` | Nothing above answered. No point: the place falls back to its county, and the product says so. |

A description that doesn't single out one place is never resolved by guessing. Eleven sites
(about 1,700 MW of waiting projects) are still at county level for that reason.

`tests/integration/test_load.py` checks every point against the dataset it cites: the row has
to exist in the copy committed under `data/`, within a kilometre of the point recorded here.
