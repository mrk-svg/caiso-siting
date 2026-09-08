# Data sources and their licences

The code is MIT. The data it processes is not ours; each source carries its own terms and this
project redistributes only derived aggregates, never the raw files (they are gitignored).

| Source | What we use | Terms | Attribution required in outputs |
|---|---|---|---|
| CAISO Public Queue Report | project rows, statuses, POIs | Public information published by the California ISO; CAISO makes no warranty | "Source: California ISO Public Queue Report, run date YYYY-MM-DD" |
| CAISO Cluster 15 Queue Report | project rows | as above | "Source: California ISO Cluster 15 Queue Report (posted 2026-07-16)" |
| CAISO TPD allocation cycle results (2024, 2025 xlsx) | per-request allocated deliverability | public information published by CAISO | "Source: California ISO 2025 Transmission Plan Deliverability Allocation Cycle Results (posted 2026-05-04)" |
| CAISO market notices (e.g. PG&E POI availability for Cluster 16) | per-POI availability statements | public notices | link to the notice; encoded only where the notice names the POI |
| OpenStreetMap (via Overpass) | substation names and coordinates | ODbL 1.0 — **attribution and share-alike for derived databases** | "© OpenStreetMap contributors, ODbL" on every map and on `poi_geocode.csv` |
| Kings County GIS (parcels, general plan) | parcel APN, acreage, AG flag, GP designation | public county GIS; owner names withheld under Cal. Gov. Code §7928.205 | "Source: Kings County GIS" |
| Kern County GIS (zoning) | zoning district polygons | public county GIS | "Source: Kern County GIS (KernGIS)" |
| CEC GIS open data (transmission lines, exclusion layers) | geometry for line POIs, siting screens | CEC open data, provided "as is" | "Source: California Energy Commission GIS" |

Rules we follow:
1. Raw downloads are never committed. Snapshots keep only the parsed `projects.csv` (derived).
2. Every output row carries `source_file`, `source_run_date`, `pipeline_commit`, `pipeline_run`.
3. OSM-derived coordinates are marked by `geo_method` and the ODbL notice appears on the map and site.
4. No owner names, ever, even where a county layer leaks them.
