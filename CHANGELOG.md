# Changelog

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
