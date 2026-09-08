# Changelog

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
