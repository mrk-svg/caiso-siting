# Data dictionary

Every column, its unit, its source and its caveat. If a number in a note or a node page cannot be traced to a row here, it does not get published.

## Provenance columns (on every output)

| column | meaning |
|---|---|
| `source_file` | the CAISO file(s) the row was derived from |
| `source_run_date` | the "Report Run Date" CAISO stamps inside the Public Queue Report (blank for the Cluster 15 report, which carries none) |
| `pipeline_commit` | short git hash of the code that produced the row |
| `pipeline_run` | UTC timestamp of the run |

## `outputs/projects_all.csv` — one row per project, Public Queue Report (Cluster 14 and earlier)

| column | unit | source column | caveat |
|---|---|---|---|
| `project_name` | text | Project Name | withdrawn sheet publishes "Project Name - Confidential" |
| `queue_position` | text | Queue Position | CAISO's identifier; "1A", "22", "2207"… — join key across snapshots |
| `request_received`, `queue_date` | date | Interconnection Request Receive Date, Queue Date | |
| `status` | text | Application Status | ACTIVE / COMPLETED / WITHDRAWN as CAISO writes it |
| `sheet_status` | text | (sheet) | which of the three sheets the row came from — the authoritative status |
| `study_process` | text | Study Process | "C14", "SERIAL LGIP", "AMEND 39"… |
| `cluster` | text | derived | `study_process` normalised; "Cluster 14" → "CLUSTER 14" where CAISO spells it out, else the raw code |
| `type_1..3`, `fuel_1..3`, `mw_1..3` | text / MW | Type-n, Fuel-n, MW-n | up to three generating components |
| `net_mw` | MW | Net MWs to Grid | net at the POI |
| `poi_mw` | MW | = `net_mw` | the figure to use whenever "capacity" is meant |
| `storage_mw` | MW | derived | sum of `mw_n` where the component is Storage/Battery; **can exceed `net_mw` for hybrids** |
| `has_storage`, `has_solar`, `has_wind`, `is_standalone_storage` | bool | derived from types/fuels | |
| `deliverability` | text | Full Capacity, Partial or Energy Only | FULL CAPACITY / PARTIAL CAPACITY / ENERGY ONLY |
| `tpd_pct` | % | TPD Allocation Percentage | |
| `tpd_group` | text | TPD Allocation Group | CAISO's allocation group letter/number |
| `offpeak_deliverability` | text | Off-Peak Deliverability and Economic Only | |
| `county` | text | County | **normalised** (`common.clean_county`); multi-county kept as "A/B", sorted |
| `state` | text | State | CA / NV / AZ / MX |
| `utility` | text | Utility | PTO code: PGAE, SCE, SDGE, GLW, DCRT, LSPC, WAPA… |
| `pto_region` | text | PTO Study Region | |
| `poi` | text | Station or Transmission Line | **free text** as filed |
| `poi_base` | text | derived | `poi` with the voltage suffix stripped — display label only |
| `node_key` | text | derived | `common.norm_poi(poi)` — the join key for nodes; "WHIRLWIND SUBSTATION 230 kV", "Whirlwind", "WHIRLWIND SUB" all → "WHIRLWIND" |
| `proposed_cod`, `current_cod`, `actual_cod` | date | Proposed / Current / Actual On-line Date | `actual_cod` only on the completed sheet |
| `suspension_status` | text | Suspension Status | |
| `study_feasibility`, `study_sis_phase1`, `study_fas_phase2`, `study_optional` | text | study columns | "Complete", "Waived", "In Progress", blank |
| `ia_status` | text | Interconnection Agreement Status | Executed / In Progress / Filed Unexecuted |
| `withdrawn_date`, `withdrawn_year` | date / year | Withdrawn Date | withdrawn sheet only |
| `withdrawal_reason` | text | Reason for Withdrawal | almost always "IC Request" or blank — **carries no cause** |
| `withdrew_post_phase2` | bool | derived | withdrawn AND Phase II / Facilities Study marked Complete — a stage signal, not a cause |
| `queue_year` | year | derived from `queue_date` | |

## `outputs/cluster15_projects.csv` — one row per project, Cluster 15 report

Same canonical names where the concept matches. Differences:

| column | source column | caveat |
|---|---|---|
| `queue_position` | Queue Number | CAISO queue position (4-digit); no overlap with the public report today — `nodes.load_projects` drops any that appear in both |
| `project_number` | Project Number | CAISO internal id |
| `net_mw` / `poi_mw` | NET MW POI | |
| `study_area` | Study Area | "PG&E FRESNO", "SCE METRO"… |
| `utility` | PTO | |
| `poi_kv` | Voltage kV | |
| `service_type` | Service Type | requested, not granted |
| `deliverability` | derived | "FULL CAPACITY (REQ)" / "ENERGY ONLY (REQ)" — **requested**, nothing is allocated for C15 yet |
| `is_merchant` | derived | service type contains "MERCHANT" |
| `withdrawn_date` | Withdrawal Date | withdrawn sheet only |
| `county` | PROJECT COUNTY | hand-typed by CAISO; normalised the same way |
| `withdrew_post_phase2` | constant False | no Phase II results exist for C15 |

## `outputs/nodes.csv` — one row per node (`node_key`)

| column | unit | definition | quote it? |
|---|---|---|---|
| `node_key`, `poi_base`, `county`, `utility` | | key; most common label/county/utility across both reports | |
| `legacy_active_projects/_mw/_storage_mw` | n / MW | ACTIVE rows in the public report | yes |
| `c15_active_projects/_mw/_storage_mw` | n / MW | ACTIVE rows in the C15 report | yes |
| `operating_projects/_mw/_storage_mw` | n / MW | COMPLETED rows in the public report | yes |
| `pipeline_mw`, `pipeline_storage_mw` | MW | legacy active + C15 active | yes |
| `wd_alltime_projects/_mw/_storage_mw` | n / MW | every withdrawn row since 2006, both reports | historical colour only |
| `wd_recent_projects/_mw/_storage_mw` | n / MW | withdrawn in the last `RECENT_YEARS` (5) years, both reports | yes |
| `c15_withdrawn_projects/_mw/_storage_mw` | n / MW | withdrawn rows in the C15 report | yes |
| `wd_post_phase2_mw` | MW | public-report withdrawals with Phase II/FAS complete | yes, as a stage signal; **never as a cause** |
| `c15_fcds_req_mw` | MW | C15 active MW that *requested* Full Capacity | yes, with the word "requested" |
| `storage_churn` | ratio | `wd_recent_storage_mw ÷ (pipeline_storage_mw + operating_storage_mw)`; NaN when no storage survives | **the churn number to quote** |
| `churn_alltime` | ratio | `wd_alltime_mw ÷ (pipeline_mw + operating_mw)` | no — dominated by 2008–2015 wind/solar |
| `c15_survival` | ratio | `c15_active_mw ÷ (c15_active_mw + c15_withdrawn_mw)` | yes |
| `c16_poi_status`, `c16_poi_note` | text | latest official statement in `data/poi_availability.csv` for this node: AVAILABLE / UNAVAILABLE / CONDITIONAL / RELIEVED; blank = **no statement**, not availability | yes, citing the notice |
| `lat`, `lon` | deg | position, see `geo_method` | only with the method stated |
| `geo_method` | text | `override` (hand-verified, sourced) · `exact` (OSM name) · `line-midpoint` (both ends found) · `fuzzy` (≥0.85, same first token) · `line-one-end` (**one end of a line, not the tap**) · `override-approx` (±km) · `county-centroid` (**position unknown**; median of located nodes in the county) · `none` | |
| `geo_score` | 0–1 | 1.0 override/exact; fuzzy ratio; ×0.7 for line-one-end; 0.8 approx; 0.3 centroid | |
| `osm_name` | text | matched OSM feature, or the override note | |

## `outputs/poi_geocode.csv` — every node's geocode decision (audit this before publishing a map)

`node_key, poi_base, lat, lon, osm_name, geo_score, geo_method` — same definitions as above.

## `outputs/by_county.csv`, `by_poi.csv`, `by_cluster.csv`, `withdrawals_by_year.csv`, `deliverability.csv`

Public-report-only aggregates from `caiso-siting queue`. `by_poi.csv` groups on `poi_base` (raw label), not `node_key` — use `nodes.csv` for anything cross-report.

## `data/snapshots/YYYY-MM-DD/projects.csv` and `outputs/diff_latest.csv`

Snapshot: the `TRACKED` columns of both reports keyed `PUBLIC:<queue_position>` / `C15:<queue_position>`. Diff rows: `key, change, project, poi, county, mw, detail` where `change` ∈ NEW, GONE, WITHDRAWN, COMPLETED, STATUS, MW_CHANGE, COD_SLIP, COD_PULLED_IN, IA_STATUS, DELIV_CHANGE, POI_CHANGE and `detail` is "old -> new".

## `data/poi_overrides.csv` (hand-maintained)

`poi, lat, lon, approx, note` — `note` must name the source (notice + DMS string, OSM way id, …). `approx=yes` marks a position known only to a few km.

## `data/poi_availability.csv` (hand-maintained)

`poi, utility, status, note, source, date` — one row per POI per notice. Encode only what a source says by name. Latest `date` wins in the join.

## `outputs/parcels_<name>.csv`

`county, apn, acres, ag, community, township, range_, lat, lon, km_to_poi` + one column per overlay (`kings_general_plan`, `kern_zoning`). No owner names — counties withhold them by statute, and this project would not publish them if they didn't.
