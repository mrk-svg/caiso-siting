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
| `storage_component_mw` | MW | derived | raw nameplate sum of `mw_n` where the component is Storage/Battery — uncapped, so it **can exceed `net_mw`** for hybrids |
| `storage_mw` | MW | derived | `storage_component_mw` capped at `net_mw` — the figure any ratio may use. Filings that report `net_mw` as 0 keep the component MW (the battery is not erased), so a handful of rows still exceed their net-to-grid figure |
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
| `node_key`, `poi_base`, `county`, `utility`, `state` | | key; most common label/county/utility/state (CA / NV / AZ / MX) across both reports | |
| `legacy_active_projects/_mw/_storage_mw` | n / MW | ACTIVE rows in the public report | yes |
| `c15_active_projects/_mw/_storage_mw` | n / MW | ACTIVE rows in the C15 report | yes |
| `operating_projects/_mw/_storage_mw` | n / MW | COMPLETED rows in the public report | yes |
| `pipeline_mw`, `pipeline_storage_mw` | MW | legacy active + C15 active | yes |
| `wd_alltime_projects/_mw/_storage_mw` | n / MW | every withdrawn row since 2006, both reports | historical colour only |
| `wd_recent_projects/_mw/_storage_mw` | n / MW | withdrawn in `RECENT_FROM_YEAR`…this year, both reports (a calendar-year window; the current year is partial). `_storage_mw` is the storage MW of those rows, each project's storage components capped at its net-to-grid figure — the handful of filings that report net-to-grid as 0 keep the component MW, so `wd_recent_storage_mw` exceeds `wd_recent_mw` at 3 nodes today | yes |
| `c15_withdrawn_projects/_mw/_storage_mw` | n / MW | withdrawn rows in the C15 report | yes |
| `wd_post_phase2_mw` | MW | public-report withdrawals with Phase II/FAS complete | yes, as a stage signal; **never as a cause** |
| `c15_fcds_req_mw` | MW | C15 active MW that *requested* Full Capacity | yes, with the word "requested" |
| `storage_churn` | ratio | `wd_recent_storage_mw ÷ (pipeline_storage_mw + operating_storage_mw)`; NaN when no storage survives | **the churn number to quote** |
| `churn_alltime` | ratio | `wd_alltime_mw ÷ (pipeline_mw + operating_mw)` | no — dominated by 2008–2015 wind/solar |
| `c15_survival` | ratio | `c15_active_mw ÷ (c15_active_mw + c15_withdrawn_mw)` | yes |
| `tpd25_projects` | n | projects at the node that sought TPD in CAISO's 2025 allocation cycle (results xlsx posted 2026-05-04) | yes |
| `tpd25_req_mw` | MW | MW those requests asked for | yes |
| `tpd25_alloc_mw` | MW | requested × allocation % | yes — this is *allocated* deliverability, the column the C15 "requested" figures lack |
| `tpd25_denied_mw` | MW | MW requested by rows that received exactly 0 % — refused outright | yes; the file states no reason and neither may you |
| `tpd25_unalloc_mw` | MW | `tpd25_req_mw − tpd25_alloc_mw`: MW refused outright **plus** the remainder left by partial allocations | yes — **this is "what the developer did not get"**, and the number to quote over `tpd25_denied_mw` |
| `tpd25_unknown_mw` | MW | MW requested by rows carrying no allocation percentage in the file; 0 today | yes, as a completeness check |
| `tpd24_fcdsa_projects`, `tpd24_pcdsa_projects` | n | projects allocated Full / Partial Capacity in the 2024 cycle (that file carries no MW) | yes |
| `tpd25_req_A_mw` … `tpd25_req_D_mw`, `tpd25_denied_A_mw` … `tpd25_denied_D_mw` | MW | the same request / refused MW split by CAISO allocation group: A = executed PPA (or LSE own load), B = shortlisted / negotiating a PPA, C = already operating, D = no PPA, Section 8.9.2.3 path (2025 TPD Allocation Report, 2026-04-13) | yes — say the group |
| `tpd25_denied_ppa_mw` | MW | refused MW in groups A + B: contracted or shortlisted projects that did not get deliverability | yes — **the refusal that matters**; a 0 % in group D is the expected result for an uncontracted project |
| `lcr_area`, `lcr_sub_area`, `lcr_status`, `lcr_note`, `lcr_source` | text | Local Capacity Area (Resource Adequacy geography) from `data/lcr_areas.csv`: `lcr_status` is `in <area>` or `outside <area>` as the LCT report's boundary lists state it; blank = **not encoded**, never "outside every area" | yes, citing the report; quote `lcr_note` where it carries a voltage split |
| `wdat_active_projects`, `wdat_active_mw` | n / MW | ACTIVE requests in the wholesale distribution (WDAT) queue at the **same substation** — `data/wdat_pge.xlsx`, PG&E only today. A WDAT request connects below CAISO's transmission grid and carries **no CAISO deliverability** unless separately studied | yes, never as CAISO pipeline |
| `wdat_active_storage_mw` | MW | storage MW attributed from `wdat_active_mw` — **an assumption**: the PG&E file publishes one MW figure per request, so storage-only requests count in full and solar+storage requests count at half. Today: 160 of 1,011 active requests carry storage, and 362 of their 479 MW is attributed as storage. The split is not published | only with the assumption stated |
| `wdat_inservice_mw` | MW | WDAT MW already in service at that substation | yes |
| `wdat_withdrawn_mw` | MW | WDAT MW withdrawn at that substation (all-time in the file) | yes |
| `lmp_tb4_12mo_mean` | $/MWh | TB4 spread of day-ahead LMP at the confirmed PNode (`data/poi_pnodes.csv`): mean over every day fetched of (mean of the 4 highest hourly DAM LMPs − mean of the 4 lowest). NaN unless the node has a confirmed PNode and `caiso-siting oasis fetch` has run | yes, as **a first-pass storage revenue screen, not a revenue forecast** — energy arbitrage with perfect foresight, no RA, no AS, no real-time, no losses |
| `lmp_tb4_12mo_p90` | $/MWh | 90th percentile of the same daily TB4 spread | with the same caveat |
| `lmp_months` | n | months of OASIS data behind the two numbers; 0 = nothing fetched for this node | |
| `c16_poi_status`, `c16_poi_note` | text | latest official statement in `data/poi_availability.csv` for this node: AVAILABLE / UNAVAILABLE / CONDITIONAL / RELIEVED; blank = **no statement**, not availability | yes, citing the notice |
| `lat`, `lon` | deg | position, see `geo_method` | only with the method stated |
| `geo_method` | text | `override` (hand-verified, sourced) · `exact` (OSM name) · `line-midpoint` (both ends found) · `fuzzy` (≥0.85, same first token) · `line-one-end` (**one end of a line, not the tap**) · `override-approx` (±km) · `cec-line` (on the CEC transmission-line geometry from `caiso-siting layers lines`; nearest vertex to the county's located nodes, else length-midpoint — on the right line, still not the exact tap) · `ambiguous` (an exact OSM name match, but features sharing that name sit more than `AMBIGUOUS_KM` (50 km) apart — **the position may be the wrong one**) · `state-mismatch` (the matched position was provably outside the filed state and was rejected; the node falls back to a county centroid) · `county-centroid` (**position unknown**; median of located nodes in the county) · `none` | |
| `geo_score` | 0–1 | 1.0 override/exact; fuzzy ratio; ×0.7 for line-one-end; 0.8 approx; 0.5 ambiguous; 0.3 centroid; 0.0 state-mismatch | |
| `osm_name` | text | matched OSM feature, or the override note | |

## `outputs/tpd_allocations.csv` — one row per TPD allocation request

`tpd_year, pto, queue_id, allocation_group, status (FCDSA/PCDSA/NONE), allocation_pct, mw_requested (2025 only), mw_allocated, in_generator_queue` + provenance.
Rows whose `queue_id` is a WDAT number, `-WD`, `CONV` or a PTO code are distribution-level or conversion requests; they do not join to nodes.

## `outputs/wdat_projects.csv` — one row per wholesale distribution (WDAT) request

From `caiso-siting wdat` over `data/wdat_pge.xlsx` (PG&E's Wholesale Distribution Queue; PG&E is the only PTO
publishing one today). These requests connect **below** CAISO's transmission grid: they are not in the CAISO queue and
carry **no CAISO deliverability** unless separately studied. Never add their MW to pipeline MW.

`request_received, queue_position, process_applied, process, status, proposed_cod, current_cod, actual_cod, county,
poi, gen_type, net_mw, ia_status, notes, utility, status_raw, sheet_status, poi_mw, has_storage, has_solar,
is_standalone_storage, storage_mw, poi_base, node_key, queue_year, cluster` + provenance.

| column | meaning |
|---|---|
| `status_raw` / `sheet_status` | PG&E's own word ("Active", "In Service", "Withdrawn") / normalised ACTIVE / COMPLETED / WITHDRAWN |
| `process` | Fast Track / Detailed Study / Independent Study / DGSP / Cluster |
| `net_mw` | the single MW figure the file publishes per request — there is no per-component breakdown |
| `storage_mw` | **an assumption**: `net_mw` for a storage-only request, half for a solar+storage request, 0 otherwise (160 of 1,011 active requests carry storage; 362 of their 479 MW is attributed). The split is not published — say so whenever you quote it |
| `node_key` | `common.norm_poi(Substation)`, so a WDAT substation that is also a CAISO POI lands on the same node |

WDAT queue numbers ("2179-WD") are the ids the TPD allocation files use for distribution-level requests, so
`outputs/tpd_allocations.csv` rows with `in_generator_queue == False` join here on `queue_position`.

## `outputs/poi_geocode.csv` — every node's geocode decision (audit this before publishing a map)

`node_key, poi_base, lat, lon, osm_name, geo_score, geo_method` — same definitions as above.

## `outputs/survival_by_cluster.csv` — Kaplan–Meier survival, one row per cohort × month

From `caiso-siting survival`. Cohorts: `C10`…`C14` (`cluster` in the public report), `C15` (the Cluster 15 report, after `nodes.load_projects` dedupe), and `C13-C15 standalone storage` / `C13-C15 solar+storage` / `C13-C15 other` (C13, C14 and C15 combined, split on `is_standalone_storage`, then `has_solar & has_storage`, then the rest).

| column | unit | definition |
|---|---|---|
| `cohort` | text | cohort name as above |
| `month` | months | 0…120, months since `queue_date` (days ÷ 30.4375, rounded to the nearest month) |
| `at_risk` | n | projects with `t >= month` — still in the queue and not yet censored at the start of that month |
| `events` | n | withdrawals at that month |
| `survival` | 0–1 | Kaplan–Meier S(t) = ∏ (1 − events ÷ at_risk) over months ≤ t; **share of the cohort not yet withdrawn**. NaN once fewer than 5 projects remain at risk |
| `survival_mw_weighted` | 0–1 | the same product with each project weighted by `net_mw` (NaN MW counts as 0) |

**Censoring rule.** Event = withdrawal at `withdrawn_date`. ACTIVE rows are right-censored at the public report's `source_run_date` (Cluster 15 rows use the same date; the C15 file has no run date). COMPLETED rows are **not** events — completion is the success outcome — and are censored at `actual_cod` when present and not after the run date, else at the run date. Rows with no `queue_date`, withdrawn rows with no `withdrawn_date`, and rows whose end date precedes the queue date are excluded and counted in the summary. "Survival" means *not yet withdrawn*; it is not failure and carries no cause.

## `outputs/survival_summary.csv` — one row per cohort

| column | unit | definition |
|---|---|---|
| `n`, `events`, `censored` | n | projects analysed; withdrawals; active or completed rows censored |
| `mw_total`, `mw_withdrawn` | MW | `net_mw` summed over `n`, and over the events |
| `follow_up_months` | months | last month at which S(t) is reported (≥ 5 projects still at risk) |
| `median_survival_months` | months | first month with S(t) ≤ 0.5; blank = not reached within follow-up |
| `s12`, `s24`, `s36`, `s48`, `s60` | 0–1 | S(t) at 12…60 months; blank when beyond `follow_up_months` |
| `s12_mw` … `s60_mw` | 0–1 | the MW-weighted S(t) at the same horizons |
| `excluded_no_queue_date`, `excluded_withdrawn_no_date`, `excluded_end_before_queue` | n | rows dropped under the censoring rule above |

`outputs/survival.svg` and `survival_tech.svg` are the step charts of `survival` for the cluster cohorts and the technology split; `survival.md` is the summary table plus the computed findings.

## `outputs/by_county.csv`, `by_poi.csv`, `by_cluster.csv`, `withdrawals_by_year.csv`, `deliverability.csv`

Public-report-only aggregates from `caiso-siting queue`. `by_poi.csv` groups on `poi_base` (raw label), not `node_key` — use `nodes.csv` for anything cross-report.

## `data/snapshots/YYYY-MM-DD/projects.csv` and `outputs/diff_latest.csv`

Snapshot: the `TRACKED` columns of both reports keyed `PUBLIC:<queue_position>` / `C15:<queue_position>`. Diff rows: `key, change, project, poi, county, mw, detail` where `change` ∈ NEW, GONE, WITHDRAWN, COMPLETED, STATUS, MW_CHANGE, COD_SLIP, COD_PULLED_IN, IA_STATUS, DELIV_CHANGE, POI_CHANGE and `detail` is "old -> new".

## `data/poi_overrides.csv` (hand-maintained)

`poi, lat, lon, approx, note` — `note` must name the source (notice + DMS string, OSM way id, …). `approx=yes` marks a position known only to a few km.

## `data/poi_availability.csv` (hand-maintained)

`poi, utility, status, note, source, date` — one row per POI per notice. Encode only what a source says by name. Latest `date` wins in the join.

## `data/lcr_areas.csv` (hand-maintained) — substation → Local Capacity Area

`substation, utility, lcr_area, lcr_sub_area, relation (in|out), note, source, source_date`. Encoded from the
"substations that delineate the area" lists in CAISO's Local Capacity Technical Report (section 3.3.x.1 of each area).
The report names boundary stations only. A station whose low-voltage bus is in and high-voltage yard is out (Gates
70 kV in, 230 kV out) is encoded `out` with a note, because queue POIs sit on the high side. `utility` disambiguates
same-name stations (Eagle Rock: PG&E vs SCE). Values must not contain `#`.

## `outputs/tpd_node_rows.csv` — one row per TPD allocation request, joined to its node

`node_key, tpd_year, queue_id, project_name, allocation_group, status, mw_requested, allocation_pct, mw_allocated`
— the rows behind each node page's "TPD allocation requests at this node" table.

## `data/poi_pnodes.csv` (hand-maintained) — node → OASIS pricing node

`node_key, pnode, confirmed, note`. Only rows with `confirmed == yes` **and** a non-empty `pnode` are ever queried; everything else is ignored by `oasis fetch`. `caiso-siting oasis suggest` writes candidates for the top-N nodes by `pipeline_mw` with `confirmed=no` and the fuzzy score (plus alternatives) in `note`; it never overwrites a confirmed row. PNode ids are **never guessed by code** — look each one up in `data/pnodes.csv` (the ATL_PNODE list from `caiso-siting oasis pnodes`, gitignored) and flip `confirmed` to `yes` by hand. A POI's substation can carry several PNodes (generator buses, load aggregation points); the one to confirm is the generator node at the interconnection bus, and `note` should say which and why.

## `outputs/lmp_tb4.csv` — one row per confirmed node × month, day-ahead LMP

From `caiso-siting oasis fetch --months 12` (run from a terminal; OASIS is rate-limited and the client waits ~5 s between calls). Source query: OASIS SingleZip `PRC_LMP`, `market_run_id=DAM`, `LMP_TYPE=LMP` (the total; MCE/MCC/MCL components are dropped), one request per month, raw CSV cached under `data/oasis_cache/<pnode>/<YYYY-MM>.csv` (gitignored; cached months are never re-downloaded).

| column | unit | definition |
|---|---|---|
| `node_key`, `pnode` | text | node and the confirmed OASIS PNode it was queried as |
| `month` | YYYY-MM | operating month (`OPR_DT`, Pacific) |
| `days` | n | operating days with at least 8 hourly prices (short spill-over days are dropped) |
| `tb4_mean` | $/MWh | mean over those days of the daily TB4 spread = mean of the 4 highest hourly LMPs − mean of the 4 lowest |
| `tb4_p90` | $/MWh | 90th percentile of the daily TB4 spread |
| `lmp_mean` | $/MWh | mean of the daily mean LMP |

TB4 is the energy-arbitrage a 4-hour battery with perfect foresight would earn per MWh of capacity on the day-ahead market alone. It is **a first-pass storage revenue screen, not a revenue forecast**: no RA, no ancillary services, no real-time market, no losses, no degradation, no charging constraints.

## `outputs/lmp_tb4_summary.csv` — one row per confirmed node

`node_key, pnode, months, tb4_12mo_mean, tb4_12mo_p90, lmp_12mo_mean, first_month, last_month` + provenance — the same statistics over every day in the fetched window (12 months by default; `months` says how many actually came back). This is what `nodes.join_lmp` reads into `nodes.csv`.

## `outputs/parcels_<name>.csv`

`county, apn, acres, ag, community, township, range_, lat, lon, km_to_poi` + one column per overlay (`kings_general_plan`, `kern_zoning`).
After `caiso-siting layers screen`: `williamson_act` (Prime / Nonprime / Nonrenewal / FSZ / Mixed / enrolled / blank — DOC 2025 layer, by APN then by polygon) and booleans `excl_base_solar`, `excl_protected_solar`, `excl_technoeconomic_solar`, `tribal_land`, `critical_habitat` (parcel centroid inside a CEC screen polygon). Presence only — the CEC screen layers carry no attributes. No owner names — counties withhold them by statute, and this project would not publish them if they didn't.
