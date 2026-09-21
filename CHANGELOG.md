# Changelog

## 1.7.3 — 2026-09-21 — pin the runner image

Both workflows now run on `ubuntu-24.04` instead of `ubuntu-latest`. GitHub moves `ubuntu-latest` to
Ubuntu 26 on 2026-10-19, underneath an unattended weekly job — the same class of silent environment
change that made the CSV formula guard inert when CI began resolving pandas 3. The image now changes
only by commit. `tests/test_packaging.py` fails if any workflow goes back to a moving label. The pin
must be bumped by hand before GitHub retires Ubuntu 24.04 runners.

## 1.7.2 — 2026-09-21 — the weekly commit step could not survive new CAISO data

Weekly run #5 failed with exit code 128 — a git error, not a pipeline error: the download and the
whole pipeline had already succeeded. The commit step staged its outputs by glob and missed three
files that are tracked and rewritten every time CAISO publishes: `outputs/survival.svg`,
`outputs/survival_tech.svg` and `data/documents_seen.csv`. Left unstaged, they made
`git pull --rebase` refuse to run ("You have unstaged changes"), which git reports as 128. The bug
had been latent since those files were first committed; this Monday was the first weekly run with a
new CAISO run date since then, so it was the first run that reached the commit. The step now runs
`git add -u` after the globs, prints `git status --short` so a future failure shows what it was
holding, and rebases with `--autostash`. `tests/test_packaging.py` fails if either is removed.
Nothing was published by the failed run: the deploy job was skipped.

## 1.7.1 — 2026-09-16 — fix the CI failure v1.7.0 introduced

**The dependency audit could never pass.** `pip-audit --strict` was pointed at the installed
environment, which includes this project itself via `pip install -e .`; pip-audit cannot resolve a
local editable distribution on PyPI, and under `--strict` that unresolvable entry is an error. Every
run failed regardless of whether a real advisory existed — `--skip-editable` does not help, since a
skip is also an error under `--strict`. The job now audits the declared dependencies
(`-r requirements.txt`), which is what actually gets installed anyway. `requirements.txt` was dead
weight duplicating `pyproject.toml` and missing `numpy`; it is now the audited artifact, and
`tests/test_packaging.py` fails if the two ever disagree, or if the version in `pyproject.toml`
drifts from the newest changelog entry.

**The CSV formula guard did nothing on pandas 3.** `csv_safe` tested `dtype != object` to find text
columns. pandas 3 gives string columns a dedicated `str` dtype, so every text column was skipped and
the escape ran on nothing — while passing its own test on pandas 2. CI resolves `pandas>=2.0` to
pandas 3, so the guard SECURITY.md describes was inert in exactly the environment that publishes.
Now it skips numeric columns instead of trying to name text ones, and is verified against both
major versions. The underlying exposure — bare floors, no ceilings, no lockfile — is recorded in
`KNOWN_ISSUES.md`.

**The built-site guard was a coin flip in CI.** The test that walks every built page for the
reliance line skipped when `site/` predated its source, which is the right behaviour locally but
arbitrary in a fresh checkout where every file is stamped within the same second. It now allows a
two-minute tolerance, so it runs deterministically in CI and still skips locally when the source has
genuinely moved on.

357 tests locally; 336 plus 21 data-dependent skips in a clean checkout.

## 1.7.0 — 2026-09-16 — source freshness, publication review, legal corrections

Three independent reviews — a data engineer on source freshness, an application security engineer
on the repository as a publishable artifact, and a technology-and-data-licensing attorney on legal
exposure. None was performed by a licensed professional; each read the code and the primary
documents. Their blocking findings are fixed here.

**Freshness: a missing source no longer publishes as the number zero.** Deleting `data/eia860.zip`
used to give every node `eia_nameplate_mw = 0.0`, which a reader parses as "nothing operates near
this node" rather than "we do not know"; the same pattern zeroed the TPD, WDAT and availability
columns. Those now go blank. `data/source_freshness.csv` records every source's cadence and the
age at which it is stale or expired, **measured against its own publication schedule** — an annual
report eleven months old is current, a monthly file two months old is not. `caiso-siting freshness`
reports the table; `nodes` runs it first and withholds the figures a source can no longer support.
The CAISO queue is the one source that fails the build rather than publishing under a false as-of
date. The methodology page carries a per-source as-of table, replacing a footer that printed the
queue's two-day-old date beside a sentence naming six sources, one of them 244 days old.

**Legal.** The claim that California statute redacts parcel owner names appeared in six places; the
previous release corrected one of them. Cal. Gov. Code § 7928.205 bars *agencies* from posting an
*elected or appointed official's* home address, phone, or name joined to an assessor parcel number —
it does not oblige anyone to withhold owner names, and a land broker is a named target user who was
being told otherwise. README, LICENSE-DATA, DATA.md, `parcels.py` and the three shipped parcel
summaries now say plainly that withholding is this project's policy. The ODbL grant was asserted
over all of `outputs/`, including EIA-860-derived files that are public-domain federal work; it is
narrowed to the two files that actually carry OSM-derived coordinates. `data/ATTRIBUTION.txt`
carries CAISO's required credit with the workbooks redistributed there. The outreach working files
are gitignored before they can collect named third parties in a public repository.

**The map had no disclaimer at all.** It is copied verbatim into `site/` rather than rendered, so it
bypassed the template that carries the reliance line — on the one page most likely to be shared. It
now carries the reliance text and the ODbL attribution the repository promises "on every map", and a
test walks every built page rather than naming two by hand.

**Security.** The queue report — the file the whole pipeline rests on — was written straight onto
its destination on any HTTP 200, so a captive portal or CDN error page destroyed the only local
copy. All downloads now go through `fetch.py`: HTTPS enforced on every hop, redirects refused if
they downgrade or leave a host allow-list, an 80 MB body cap, and `.part` + verify + replace.
Output CSVs are escaped against spreadsheet formula injection (`config.csv_safe`) — SECURITY.md
claimed a test for this that did not exist; the test exists now. Workflow permissions are declared
per job, so the Pages deploy no longer holds `contents: write`. Five inaccurate sentences in
SECURITY.md are corrected.

355 tests.

## 1.6.0 — 2026-09-16 — domain review: identity, positions, and a published defect register

Two independent domain review passes against the primary source documents — one checking
`data/lcr_areas.csv` row by row against the Final 2027 Local Capacity Technical Report, one
checking the outputs for physical and commercial plausibility. Neither has been confirmed by a
licensed engineer; that is the next step, not a completed one.

**Ambiguity is no longer resolved by guessing.** `county`, `utility` and `state` on a node are the
*projects'* labels, and pandas broke a tied mode alphabetically — which published PGAE on Los
Angeles County substations (`EAGLE ROCK`, `EL NIDO`) and then matched them to the wrong local
capacity row. `sole_mode` returns the modal value only when the mode is unique, blank otherwise.
`EAGLE ROCK` no longer displays "in North Coast/North Bay" on a Los Angeles substation.

**Nine proven-wrong positions quarantined.** `WALNUT` was mapped 474 km away in Stanislaus County
with `geo_method=exact` and `geo_score=1.0`; `MERCED`, `CAMDEN`, `MISSION`, `WARNER`, `OLINDA`,
`SAN MATEO`, `MUSTANG` and `MERCED CIRCUIT` were similarly matched to same-named substations on
the wrong utility's system. `data/geo_quarantine.csv` lists them with the evidence; they now carry
no position, read as `disputed`, and are excluded from the map and from the EIA distance join. A
confidently wrong coordinate is worse than no coordinate, because it is drawn and it wins joins.

**Four local-capacity corrections, each quoted to a report page.** `Bellota` moved to `out`: the
note claimed every queue POI there is 115 kV, but the only *active* POI is 230 kV (Belterra, 500
MW) and the report puts Bellota 230 kV outside — the row was overstating RA value and breaking the
file's own high-side rule. `Tranquility` loses its `Panoche` sub-area, which the report never
assigns. The seven Kern `out` rows now carry `Kern PP` as the sub-area, because the report defines
a Kern-PP sub-area boundary and no Kern *area* boundary at all; the `Magunden` note no longer
claims the area. The `Panoche` note no longer asserts a 230 kV POI majority the queue files do not
support.

**`KNOWN_ISSUES.md`** publishes every defect the review found and this release did not fix — node
identity collisions, project-county-as-substation-county, the 5 km EIA attribution radius, EIA
respondent errors that make one-hour batteries, PG&E Fast Track rows above the tariff ceiling,
boundary-only local capacity coverage. A tool whose claim is traceability cannot keep a private
list of where it is wrong.

**Legal.** `DATA_LICENSES.md` cited Cal. Gov. Code § 7928.205 as the reason parcel owner names are
withheld. The section actually bars *agencies* from posting an *elected or appointed official's*
home address, telephone number, or name joined to an assessor parcel number — it does not oblige
this project to withhold owner names at all. The claim is corrected: withholding is this project's
own policy, and the statute is now cited accurately for the pairing the outputs are built never to
produce. `outputs/ATTRIBUTION.txt` ships the ODbL, CAISO and EIA attribution with the files
themselves, since a CSV that travels alone carries none of the site's footer. `AI_USE.md` states
who authored what, why AI-assisted code fails as plausible wrong answers rather than crashes, and
the limits of what this project can claim copyright over.

341 tests.

## 1.5.1 — 2026-09-15 — open-source readiness: licence boundary, reliance disclaimer, supply chain

Nothing in the pipeline changed. Everything that decides whether this repository can safely be
public did.

**Licence boundary.** The code is MIT; the outputs are not, and saying otherwise would have been a
licence violation. Substation positions come from OpenStreetMap under ODbL 1.0, which is
share-alike for databases, and `outputs/nodes.csv` carries `lat`, `lon`, `osm_name` and
`geo_method` — a derivative database, not merely a produced work. `LICENSE-DATA.md` now states the
split, the attribution line reusers must carry, and the two limits CAISO's published terms impose:
credit CAISO and keep proprietary notices intact for website reports, and never commit OASIS API
responses, whose terms are narrower. `DATA_LICENSES.md` rule 1 claimed no raw download is ever
committed while two TPD workbooks were tracked; the rule now documents that exception honestly
rather than being quietly false.

**Reliance disclaimer.** The site already said no figure states a cause. It did not say what the
site *is*. `RELIANCE` now renders on every page through the same template path as the causation
line — screening tool, not engineering advice; built by an engineer who is not a licensed PE;
verify every figure against the source filing; no warranty; no affiliation. Two tests assert it
survives on every page, because a disclaimer that can be dropped by a refactor is decoration.
`DISCLAIMER.md` carries the long form.

**Supply chain.** Every `uses:` in both workflows is pinned to a commit SHA with the version in a
trailing comment, so a re-pointed upstream tag cannot execute inside a job holding a write token.
`ci.yml` gained a `pip-audit --strict` job, so a new advisory fails the build instead of waiting
for a Dependabot pull request. The pytest exit-code-5 escape hatch is gone: with 339 tests, "no
tests collected" no longer means "not written yet", it means collection broke and CI went green
anyway. `SECURITY.md` is corrected — Leaflet is vendored, not loaded from a CDN with SRI — and
now routes reports to a private advisory rather than a public issue.

**Contribution path.** `CONTRIBUTING.md` leads with the ask that matters: send a number that is
wrong, with the public filing that shows it, and no code required. A `data-correction` issue
template asks for the figure, the correction, the source and a confidence level, and both the
guide and the template tell contributors not to post anything that is not in a public filing.
`CITATION.cff` added for researchers. README gained the disclaimer, the correction ask above the
fold, and the licence split.

## 1.5.0 — 2026-09-15 — the node page a person reads before filing

The node page is rebuilt around the seven questions a developer, lender or counsel asks before filing at a POI —
can you get in; who is ahead of you; do projects leave after seeing the costs; will you be deliverable; will the
power be worth anything; will the land pass intake; how long, and who gave up. Each is answered with the sourced
figure and the project count behind it, and each carries a **Not public** line naming what the public files cannot
answer and where that answer lives (RIMS study reports, customer identity, financial security, withdrawal reasons,
begin-construction status, landowner intent, load-side queues). "Not on this site yet" is kept distinct from
"not public".

New metrics: Phase II attrition (`p2_reached_*`, `p2_withdrawn_*`, `p2_attrition` — of the MW that received Phase II
/ Facilities Study results at a node, the share that then withdrew; 43 % across the public report, 100 % at Morro
Bay, 23 % at Whirlwind), and the commitment layer (`committed_*` — ACTIVE MW with an executed interconnection
agreement; 60,302 of 74,687 MW). Every ratio now carries its project count (`churn_n`, `c15_n`, `p2_n`) and is dimmed
on the page when built on fewer than 3 projects or a denominator under 500 MW — Viejo's storage churn of 3.33 is
one withdrawal over one survivor and now reads that way.

EIA-860 connector (`eia860.py`, `caiso-siting eia860`, in `download` and `nodes`): the federal generator census joined
to nodes by distance (5 km, positioned nodes only). Answers what CAISO's files cannot — who operates and owns what
already runs near a node, its technology and vintage, battery MWh, MW in the Proposed sheet, and the CAISO pricing
node those generators report (the confirmed-PNode input `oasis.py` was waiting for). 2025 final data: 2,004 plants in
the footprint, 94 GW operable, 54 GWh of storage; 180 nodes get EIA columns. The join is by position, not POI, and
every rendering says so. Zip verified for members and executable content before parsing; public domain.

Review fixes (two adversarial passes over everything since 1.3.3): EIA-860 plants now join only to nodes whose
position is the substation itself (exact / override / cec-line) — line ends share the substation's coordinates and
were winning ties by row order (San Bernardino's 1,064 MW sat on a line node; Russell City on a line midpoint);
`eia_plants` counts plants with an operable unit; a corrupt or partial zip can no longer fail `nodes`, and
`download` verifies every zip and xlsx before it replaces a good file; zip members are size-guarded; the
person-name classifier now catches particles and suffixes (van/der/de, Jr) and withholds anything that could be a
person; the blank-BA rule is gone (CISO only). LCR: Antelope, Mercy Springs and Bellota are encoded IN — every queue
POI at those nodes is on the low-voltage bus the report puts inside — with the high-side exception in the note;
Magunden's utility corrected; same-name collisions (Mesa, Eagle Rock) are reported instead of silently skipped.
TPD 2024 counts are projects, not requests (Rio Hondo 6 → 3). C15 is censored at the latest withdrawal in the file
when CAISO has re-posted since the posting date. Markdown links escape quotes (attribute injection via a hostile
project name); `fact()` escapes its value; a ratio with no denominator reads "no denominator", not "too few
projects"; `line-midpoint` is an approximate position on node pages; "nan kV" no longer appears in CEC line names.

New `methodology.html`: sources, node definition, windows and censoring, the regime caveat, the small-number rule,
every metric definition, the not-public list, and what the site never does. Dark mode follows the system.
337 tests.

## 1.4.0 — 2026-09-14 — what a siting engineer asks in the first five minutes

Four changes from a senior-engineer critique of the published site.

- **Local Capacity Area per node** (`lcr.py`, `data/lcr_areas.csv`). For storage, location value is Resource
  Adequacy first, and local RA needs a POI inside a Local Capacity Area. Encoded from the boundary-substation lists
  in CAISO's Final 2027 Local Capacity Technical Report (118 stations, 10 areas): 38 queue nodes are inside an area
  (Moss Landing, Tranquility, Rio Hondo, Imperial Valley, Devers, Mira Loma, Otay Mesa, Contra Costa, Pittsburg,
  Lambie, Metcalf …) and 23 are named as outside one — Red Bluff, Vincent, Gates, Lugo, Tesla, Los Banos,
  Antelope, Midway: the most-queued nodes in the state carry no local RA value from those areas. A station whose
  low-voltage bus is in and high-voltage yard is out (Gates 70 vs 230 kV) is encoded out, with the note. Blank means
  "not encoded", never "outside every area". On node pages, the index, the Node Watch note.
- **TPD refusals by allocation group** (`tpd25_req_{A..D}_mw`, `tpd25_denied_{A..D}_mw`, `tpd25_denied_ppa_mw`,
  `outputs/tpd_node_rows.csv`). A 0 % in group D (no PPA) is the expected outcome; a 0 % in group A or B (executed
  or shortlisted PPA) is a contracted project refused deliverability. 2025 cycle: 8,097 of 15,007 denied MW were in
  groups A+B. Node pages now list every TPD request at the node with its group; definitions from the 2025 TPD
  Allocation Report (2026-04-13).
- **Survival curves carry the process regime.** Legend shows each cohort's queue-window year; the chart footnote
  and a regime table state that C14 entered under special FERC-approved procedures (Sept 2021; Phase I estimates
  advisory, full refund on early withdrawal if Phase II costs ran 25 %+ over) and that C15's queue date (2025-02-12)
  is the post-scoring date, so the 541 → 170 intake cut precedes its month 0. The findings text ends with the caveat:
  attrition compares regimes, not only nodes.
- **Customer names**: a critique point withdrawn on inspection — CAISO's public files carry project names only, no
  interconnection-customer column, so there was nothing to restore. Node pages already list every project.

317 tests. Data dictionary and licences updated.

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
