# Data sources and their licences

The code is MIT. The data it processes is not ours; each source carries its own terms. What licence
covers the *outputs* is a separate question with a separate answer — see `LICENSE-DATA.md`, which
explains why everything under `outputs/` and `site/` is ODbL 1.0 rather than MIT.

| Source | What we use | Terms | Attribution required in outputs |
|---|---|---|---|
| CAISO Public Queue Report | project rows, statuses, POIs | Public information published by the California ISO; CAISO makes no warranty | "Source: California ISO Public Queue Report, run date YYYY-MM-DD" |
| CAISO Cluster 15 Queue Report | project rows | as above | "Source: California ISO Cluster 15 Queue Report (posted 2026-07-16)" |
| CAISO TPD allocation cycle results (2024, 2025 xlsx) | per-request allocated deliverability | public information published by CAISO | "Source: California ISO 2025 Transmission Plan Deliverability Allocation Cycle Results (posted 2026-05-04)" |
| CAISO OASIS (PRC_LMP day-ahead LMP, ATL_PNODE pricing-node list) | hourly DAM LMP at hand-confirmed PNodes → daily TB4 spread; PNode names | public market data published by the California ISO on OASIS; CAISO makes no warranty; rate-limited — raw CSVs cached locally, never committed | "Source: CAISO OASIS PRC_LMP DAM" |
| EIA-860 (U.S. Energy Information Administration, annual bulk zip) | operating/proposed generators, storage MWh, owner and operator names, LMP node designations | U.S. federal government work, public domain; EIA asks for attribution | "Source: U.S. Energy Information Administration, Form EIA-860 (2025)" |
| CAISO Local Capacity Technical Report (Final 2027, dated 2026-04-29) | area / sub-area boundary substations → `data/lcr_areas.csv` | public information published by the California ISO; CAISO makes no warranty | "Source: California ISO Final 2027 Local Capacity Technical Report" |
| CAISO TPD Allocation Report (2025 cycle, 2026-04-13) | allocation-group definitions (A–D) | public information published by CAISO | cite when quoting a group |
| CAISO market notices (e.g. PG&E POI availability for Cluster 16) | per-POI availability statements | public notices | link to the notice; encoded only where the notice names the POI |
| OpenStreetMap (via Overpass) | substation names and coordinates | ODbL 1.0 — **attribution and share-alike for derived databases** | "© OpenStreetMap contributors, ODbL" on every map and on `poi_geocode.csv` |
| Kings County GIS (parcels, general plan) | parcel APN, acreage, AG flag, GP designation | public county GIS; **owner names are never read** — a project policy, not a statutory requirement (see note below) | "Source: Kings County GIS" |
| Kern County GIS (zoning) | zoning district polygons | public county GIS | "Source: Kern County GIS (KernGIS)" |
| CEC GIS open data (transmission lines, exclusion layers) | geometry for line POIs, siting screens | CEC open data, provided "as is" | "Source: California Energy Commission GIS" |

Rules we follow:
1. Raw downloads are not committed, with one documented exception: the two CAISO TPD allocation
   workbooks (`data/tpd_2024.xlsx`, `data/tpd_2025.xlsx`) are kept so the pipeline is reproducible
   offline. They are redistributed unmodified and with credit, under CAISO's published terms of use.
   Everything else — queue reports, EIA-860, OASIS responses, the LCT PDF — is gitignored, and
   snapshots keep only the parsed `projects.csv` (derived). OASIS responses are never committed
   under any circumstances: CAISO's API terms are narrower than its website terms.
2. Every output row carries `source_file`, `source_run_date`, `pipeline_commit`, `pipeline_run`.
3. OSM-derived coordinates are marked by `geo_method` and the ODbL notice appears on the map and site.
4. No owner names, ever, even where a county layer leaks them.

## Why owner names are withheld

County assessor and parcel records are generally public in California, and no statute obliges a
third party to withhold the owner name on an ordinary parcel. Withholding them here is this
project's own policy, adopted because a parcel-by-parcel list of named landowners next to
"here is where developers are looking" is a different and worse artifact than a siting screen,
whatever its legal status.

One statute is directly relevant and is cited accurately: **Cal. Gov. Code § 7928.205** provides
that "No state or local agency shall publicly post the home address, telephone number, or both the
name and assessor parcel number associated with the home address of any elected or appointed
official on the internet without first obtaining the written permission of that individual." That
binds agencies rather than this project, and it concerns officials rather than owners generally —
but it is the reason the combination this project most carefully never produces is a **name joined
to an assessor parcel number**. Parcel rows here carry APN, acreage and designation and no name at
all, so the prohibited pairing cannot be assembled from these outputs.

The same reasoning governs EIA-860 owner names: owners that classify as organisations are named,
owners that classify as individuals are counted and never named, and the classifier deliberately
errs toward not naming.
