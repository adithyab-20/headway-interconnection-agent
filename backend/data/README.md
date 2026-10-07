# Third-Party Data

The files in this directory are public datasets used for educational
and research purposes. They are not covered by this repository's
software license.

## CAISO Public Queue Report

File: `publicqueuereport.xlsx`

Source: California Independent System Operator (CAISO)
Website: https://www.caiso.com/

This file is used in accordance with the
[CAISO Terms of Use](https://www.caiso.com/privacy-terms-of-use).
California ISO is credited as the source. All copyright, trademark,
disclaimer, and other proprietary notices remain intact.

California ISO does not endorse this project.

## LBNL Queued Up Data

File: `LBNL_Ix_Queue_Data_File_thru2025.xlsx`

Source: Lawrence Berkeley National Laboratory and GridTracker
Dataset page: https://emp.lbl.gov/queues

Queued Up Data File © 2026 The Regents of the University of
California, through Lawrence Berkeley National Laboratory, and
GridTracker.

The dataset is licensed under the
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

California ISO, Lawrence Berkeley National Laboratory, GridTracker,
and their respective contributors do not endorse this project.

## CAISO public planning files

Files:
- `cluster-15-interconnection-requests.xlsx`: the 2023 batch of interconnection requests
- `attachment-b1-v8-constraint-mapping-2024-ipe.xlsx`: which connection points sit behind
  which transmission bottlenecks (2024 edition)
- `attachment-a-transmission-capability-estimates-for-use-in-the-cpuc-irp-process-2026.xlsx`:
  room behind each bottleneck and the cost of the next upgrade (2022 dollars)
- `approved-projects-transmission-planning-process-jul-2026.xlsx`: approved grid upgrades
  and their expected finish dates
- `board-approved-2025-2026-transmission-plan-appendix-h-projects.pdf`: the 2025–2026
  transmission plan's fact sheets (cost ranges)

Source: California Independent System Operator (CAISO), https://www.caiso.com/

Used in accordance with the
[CAISO Terms of Use](https://www.caiso.com/privacy-terms-of-use). California ISO is credited as
the source, and all notices in the files remain intact. California ISO does not endorse this
project.

## OpenStreetMap substations

File: `osm_substations_ca_nv_az.json` (substations in California, Nevada and Arizona,
fetched through the Overpass API; data as of the timestamp inside the file)

© OpenStreetMap contributors. Available under the
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/); see
https://www.openstreetmap.org/copyright. The substation positions table derived from it,
`src/interconnection_agent/places/positions.csv`, is published under the same licence.

## US Census county and state outlines

Files: `web/public/geo/counties.json` and `web/public/geo/states.json`, the map's outlines.

Made from the US Census Bureau's 2023 cartographic boundary files `cb_2023_us_county_5m` and
`cb_2023_us_state_5m` (https://www2.census.gov/geo/tiger/GENZ2023/shp/): counties of
California, Nevada and Arizona, and those states with their neighbours, simplified to a
quarter of their points with mapshaper. Public domain; the US Census Bureau is credited on
the map.
