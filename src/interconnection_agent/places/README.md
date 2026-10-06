# Reviewed place tables

These tables are applied by exact match only. They were drafted by
`scripts/propose_places.py` and reviewed by a person before being committed.

| File | What it maps |
|---|---|
| `spellings.csv` | each spelling of a connection point (tidied) → site and voltage, or a line's two end sites |
| `positions.csv` | each site → its OpenStreetMap substation and coordinates |
| `bottleneck_names.csv` | each bottleneck in CAISO's 2024 list → its entry in the 2026 cost estimates |
| `upgrade_places.csv` | each planned upgrade → the places it's at |

`positions.csv` is derived from OpenStreetMap: © OpenStreetMap contributors, available under
the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/). See
https://www.openstreetmap.org/copyright.
