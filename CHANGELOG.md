# Changelog

## 1.3.3 — 2026-09-14 — first live run

First end-to-end run on fresh downloads (CAISO run date 2026-09-14): 265 active / 74,687 MW; C15 86 active; TPD 2025
24,109 MW requested / 8,450 allocated at 71 nodes; 501/949 nodes located; 156 documents baselined by `watch`.
Two things it surfaced: the weekly diff's "Active storage MW" total moved -2 MW with no row explaining it (two
Whirlwind projects went 24 -> 23 MW storage on an unchanged net) — new `STORAGE_CHANGE` class; and a real-data test
pinned the report run date to 2026-09-07 and would have failed every week from now on — it now checks shape and
monotonicity. Workflows moved to `.github/`. 308 tests.

## 1.3.2 — 2026-09-08 — security review

Tool-driven review of the three attack surfaces (downloaded files, published site, unattended CI); see `SECURITY.md`.
Fixed: the map popup inserted source strings (POI, county, OSM name, notes) into the DOM unescaped and serialised
its data into a `<script>` block without neutralising `</` — a hostile string in a CAISO/PG&E file could have run
in every viewer's browser (stored XSS); values are now escaped in the browser and `</` is neutralised, with a
regression test. Leaflet now loads with subresource-integrity hashes. OASIS requests moved from HTTP to HTTPS.
Dependency floors raised for the two advisories in the transitive tree (urllib3 ≥ 2.7.0, idna ≥ 3.15).
Dependabot added for pip and GitHub Actions. Verified clean: every downloaded `.xlsx` inspected — no macros or
embedded executables (`wdat_pge.xlsx` carries Excel external-workbook links, ignored by pandas); all site text
passes `html.escape`; zero formula-like cells in any output CSV; no secrets in the tree; bandit reports only the
`git rev-parse` provenance call (fixed argv, no shell). 307 tests.

## 1.3.1 — 2026-09-08 — correctness

An adversarial audit of every published number found five defects that would have put wrong figures in front of
developers. All are fixed and locked by tests (306).

- **Storage MW double-counted.** Six filings list two storage components (RED BLUFF's ETERNAL: 1,407 MW pumped-storage
  + 1,400 MW battery on a 1,400 MW POI). `storage_mw` is now capped at net-to-grid — the raw sum survives as
  `storage_component_mw` — which halves RED BLUFF's storage churn from 1.62 to 0.84 and corrects 47 nodes.
- **"Last 5 years" was six calendar years** (`>= THIS_YEAR - RECENT_YEARS` = 2021–2026). Now 2022 onward, and every
  heading names the window. Two nodes in the published churn table (Los Banos–Gates #1, Delaney) drop to 0.00: all
  their withdrawals were in 2021.
- **A Nevada node was mapped into California at `exact / 1.00`.** VALLEY SWITCH (Nye NV, 2.7 GW) matched OSM's
  "Valley Substation" in Riverside CA because the picker took the highest voltage. Geocoding is now state-aware,
  positions provably outside the filed state are rejected (`state-mismatch`), names shared by features >50 km apart
  are flagged `ambiguous`, and the county-centroid fallback keys on state+county using in-state sources only.
  Five nodes were in the wrong state; now none.
- **"The cohort has shed 58% of its MW"** differenced a CAISO briefing's 145-project baseline against a 170-request
  file. Replaced with the file's own arithmetic: 30,564 MW withdrawn = 52% of the 59,013 MW that entered.
- **"Storage share"** was the label on a component-nameplate sum that exceeded its own total at 203 nodes. Relabelled
  everywhere, and the all-time withdrawn figure in the "both reports" bullet now actually covers both reports
  (412,480 MW, not 381,917).

Also: `tpd25_unalloc_mw` (requested − allocated, so partial allocations are no longer published as "denied 0" —
SCHULTE requested 187 MW, received 6, and showed 0 denied); NaN allocation percentages counted as `tpd25_unknown_mw`
rather than refusals; survival exclusions computed on raw days (a withdrawal 5 days before its queue date was
entering as a month-0 event); Cluster 15 censored at its own posting date, not the public report's later run date
(follow-up 19 → 17 months, removing two structurally event-free months); one `tech_flags` / `cap_storage_mw`
definition shared by all three parsers; `ia_status` normalised; and a crash when nothing geocodes (empty list read
as a column selection) fixed.

## 1.3.0 — 2026-09-08

WDAT layer (`wdat.py`, PG&E public queue: 4,639 requests; 99 CAISO nodes also carry active distribution-level requests). Document watch (`watch.py`): weekly diff of the CAISO/PTO pages that carry siting documents -> review queue; nothing auto-encoded. 233 tests.

Queue-cohort survival (`survival.py`, `caiso-siting survival`, in `weekly` after `nodes`): Kaplan–Meier time-to-withdrawal
by cluster C10–C15 and for C13–C15 by technology, unweighted and MW-weighted, on a monthly grid to 120 months —
`outputs/survival_by_cluster.csv`, `survival_summary.csv`, `survival.svg`, `survival_tech.svg`, `survival.md`, and the
site's Survival page. COMPLETED is censored at its on-line date, never an event.
OASIS day-ahead LMP (`oasis.py`, `caiso-siting oasis pnodes | suggest | fetch`, terminal-only, not in `weekly`): TB4 spread per day at hand-confirmed PNodes (`data/poi_pnodes.csv`, never guessed) → `outputs/lmp_tb4.csv`, `lmp_tb4_summary.csv`, and `lmp_tb4_12mo_mean/_p90`, `lmp_months` on `nodes.csv` — a first-pass storage revenue screen, not a revenue forecast.

## 1.2.0 — 2026-09-08

TPD allocation layer (`tpd.py`, `caiso-siting tpd`): CAISO's 2024 and 2025 allocation cycle results joined per node —
requested, allocated and denied MW; on node pages, the index and the Node Watch. 156 tests.
`layers.py`: CEC transmission-line placement for line POIs (cache `data/poi_lines.csv`, method `cec-line`) and Williamson Act + CEC siting screens for parcel tables. 168 tests.
Not free/public and therefore not built: per-POI network-upgrade cost tables (cluster study reports are served via RIMS login).

## 1.1.0 — 2026-09-08

Package layout (`src/caiso_siting`, `pyproject.toml`, `caiso-siting` CLI with `queue`, `cluster15`, `nodes`, `snapshot`,
`diff`, `parcels`, `site`, `weekly`, `download`). 137 tests. Provenance columns on every output row. `poi_mw`.
County-centroid fallback (hollow markers) so aggregate maps stop omitting a fifth of the MW. Static site generator
(`site/`: index, map, per-node pages, weekly diff, note) for GitHub Pages. Weekly GitHub Actions cron that downloads,
runs, snapshots, deploys and opens a diff issue. CI with ruff + pytest. MIT licence, `DATA_LICENSES.md`, `DATA.md`.

Bugs fixed (found by the test suite): CAISO's footer disclaimer was parsed as a project (counts were 266/252, now 265/251,
and it would have produced a spurious NEW/GONE line in every weekly diff); `#1`/`#2` circuit suffixes split one node into
two (987 → 949 nodes); one-sided hyphen spellings ("MIDWAY- GATES") were never split into endpoints; override path
bound at import time.

## 1.0.x — 2026-09-07

Public Queue Report and Cluster 15 parsers; node join on a normalised POI key; OSM geocoding with overrides and
the first-token fuzzy rule; official Cluster 16 POI-availability layer; corrected churn metrics (5-year window,
storage-specific, post-Phase-II); weekly diff engine; county parcel/zoning module.
