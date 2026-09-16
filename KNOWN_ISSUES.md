# Known issues

Read this before quoting any figure from this project.

Every entry below is a defect a domain review found and this project has not yet fixed. It is
published rather than tracked privately because a screening tool whose whole claim is
traceability cannot keep a private list of the places it is wrong. Fixed items move to the
CHANGELOG; this file holds only what is still live.

Last review: **2026-09-16**, two independent passes — one checking `data/lcr_areas.csv` row by row
against the Final 2027 Local Capacity Technical Report, one checking the outputs for physical and
commercial plausibility. Both reviews were AI-run against the primary documents and have **not**
been confirmed by a licensed engineer. That confirmation is the next step, not a completed one.

---

## 1. Node identity — several "nodes" are not one substation

**Severity: high. Affects node totals and any ranking by MW.**

A node is a normalised point-of-interconnection string from CAISO's filings, not a verified
substation. Consequences that are live today:

- **Same-name substations on different systems collapse into one node.** `MESA` merges PG&E's
  Mesa 230 kV in San Luis Obispo with SCE's Mesa in Monterey Park. `VICTOR` merges SCE's Victor
  230 kV at Victorville with PG&E's Victor 60 kV in San Joaquin. `VALLEY` merges SCE's Valley
  500/115 kV at Romoland, Riverside County — including a 500 MW active project and a 2024 Group A
  deliverability allocation — with Valley Electric's 138 kV and GridLiance's Valley Switch
  230 kV, both in Nye County, Nevada.
  *Partially mitigated 2026-09-16:* where the projects at a node disagree on utility, county or
  state, the label is now left blank instead of being guessed alphabetically, so the node no
  longer displays a confident wrong PTO and no longer matches the wrong local-capacity row. The
  underlying merge is not fixed.
- **One physical substation splits into several nodes:** `TESLA`/`TESLA E`; `MERCED`/`MERCED
  CIRCUIT`; `SAN BERNARDINO`/`SAN BERNADINO` (a typo carrying 38 MW operating);
  `IMPERIAL VALLEY`/`IMPERIAL VALLEY 230 KV`; `GEYERS 17 FULTON`/`GEYSERS 17 FULTON TRANSMISSION`
  (assigned to different counties); and a node literally named `5`, which is Whirlwind. The
  Tehachapi area alone produces eleven Whirlwind/Windhub/Highwind variants.
- **81 node keys are raw filing prose**, e.g. `POI IS AT A DESIGNATED GOOGLE COORDINATES`.

## 2. `county`, `state` and `utility` describe the project, not the substation

**Severity: high. This is the root cause of most position errors.**

These columns are taken from the queue rows, where county is the *generator's* county. For a
gen-tie or a remote resource it is not the substation's county — and 402 nodes are then placed at
that county's centroid. `HARRY ALLEN ELDORADO` is labelled Lincoln County, **Idaho** (a
DesertLink line in Clark County, Nevada). `EAST COUNTY` — SDG&E's ECO Substation near Jacumba,
1,573 MW of pipeline — is labelled **Baja California** with no position at all. `CONTROL`,
`BISHOP` and `OXBOW` are SCE's Owens Valley substations labelled **Nevada**. `ROUND MOUNTAIN` is
labelled Humboldt; it is in Shasta.

## 3. Positions: nine proven wrong, most of the rest approximate

**Severity: high, partially fixed.**

Nine nodes were published with a confident coordinate in the wrong half of the state — `WALNUT`
(474 km), `MUSTANG` (123 km), `MERCED` (430 km), `MERCED CIRCUIT`, `CAMDEN` (370 km), `MISSION`
(730 km), `WARNER` (980 km), `OLINDA` (820 km), `SAN MATEO` (630 km) — two of them with
`geo_method = exact` and `geo_score = 1.0`. As of 2026-09-16 they are quarantined in
`data/geo_quarantine.csv`: they carry no position, are marked `disputed`, and are excluded from
the map and from the EIA distance join. **They still need correct coordinates**, each with a
source, in `data/poi_overrides.csv`.

More broadly: of 949 nodes only 168 are `exact`, 402 are county centroids and 45 have no position.
About a quarter of all pipeline MW sits at a node with no real position, including
`TROUT CANYON` (3,000 MW), `MANNING` (2,662 MW) and `EAST COUNTY` (1,573 MW). `geo_method` is on
every row; use it.

## 4. EIA-860 columns mean "within 5 km", not "interconnected here"

**Severity: high for interpretation.**

The site labels this correctly; the raw columns in `outputs/nodes.csv` do not carry the distance.
Known consequences: `ANTELOPE` shows 817.9 MW from 35 plants that are mostly 20 MW-class
distributed solar on SCE's 66 kV subtransmission, not on Antelope's 220 kV bus. `DEVERS` shows
1,816.5 MW including 458 MW of San Gorgonio Pass wind collected on a separate 33/115 kV system.
`HARBORGEN` is credited with 201.5 MW of storage whose EIA plant name is *Cathode (Hinson) BESS*
and which belongs to `HINSON`, 2.5 km further away. `HENRIETTA` is overstated because `MUSTANG`
was mispositioned. And a plant can only ever be attributed to a node that appears in the CAISO
queue *and* has a real position, so `ETIWANDA` — which has no position — can never receive one,
and everything there is silently credited to a neighbour.

## 5. `eia_storage_mwh` carries EIA respondent errors

**Severity: medium. Not a pipeline bug; the values are copied faithfully.**

28 of 146 operable California storage units of 20 MW or more report energy capacity equal to
power capacity — a one-hour duration that no merchant battery built in California in 2021–2025
has. `Daggett 2` reports 131 MW against 4.6 MWh. Nodes showing exactly 1.00 h — `WHIRLWIND`
147/147, `GATES` 137/137 — are reporting artefacts. Do not compute duration from these columns
without checking the unit.

## 6. PG&E WDAT columns include impossible Fast Track requests

**Severity: medium.**

32 rows flagged "Fast Track" exceed PG&E's 5 MW Fast Track ceiling, totalling 1,281 MW — one is a
157 MW solar request at Milpitas, which cannot connect to a distribution feeder at all and is
almost certainly kW entered as MW in PG&E's posting. They are summed into `wdat_active_mw`, so
`MILPITAS`, `SAN LEANDRO U`, `STONE`, `SANGER`, `KERMAN` and `WESTPARK` are overstated. Also note
that only PG&E publishes a WDAT file: `wdat_*` is blank for every SCE and SDG&E node, which is
absence of data, not absence of queue.

## 7. Local capacity coverage is boundary-only

**Severity: medium.**

`data/lcr_areas.csv` encodes the substations the LCT report names as *delineating* each area. It
does not encode interior membership, because the report publishes no in-document roster of it. So
62 of 949 nodes carry a status and 887 are blank — and the site renders "in", "outside" or
nothing, which makes "not encoded" indistinguishable from "outside everything". Nodes plainly
inside an area and currently blank include `LAGUNA BELL` (1,750 MW), `MOORPARK` (1,500 MW) and
`VESTAL` (700 MW). `WHEELER RIDGE` is named as inside in the report and has no row at all; adding
one needs a voltage-specific note, since the report's statement is about the 115 kV junction while
the active POI is 230 kV.

Sub-area membership shown only in the report's one-line diagrams could not be verified at all —
those figures do not extract as text. Roughly 30 sub-areas rest on limiting-facility tables rather
than a checked membership list.

## 8. Ratio columns can exceed 1 and are often computed on tiny denominators

**Severity: medium.**

`storage_churn` is withdrawn MW over surviving MW, so it is not a percentage: `VICTOR` is 14.40,
`ESCONDIDO` 13.64. `c15_survival` exists for 83 nodes, 70 of which have two or fewer Cluster 15
projects. The site dims small-n ratios; the CSV does not.

## 9. No voltage class in `outputs/nodes.csv`

**Severity: medium.**

The source carries POI voltage and the node table does not, so a reader cannot distinguish a
500 kV hub from a 60 kV distribution bus while reading MW totals. That matters: 260 MW is filed at
`WEBER 60 KV`, which is roughly 2,500 A on a bus class typically rated 1,200–2,000 A. These are
filings as made, not pipeline errors, but the product gives a reader no way to apply the check.

## 10. Freshness: what is still not wired

`data/source_freshness.csv` and `caiso-siting freshness` now check every source against its own
publication cadence, and the pipeline withholds figures rather than publishing zeros for a source
it cannot honour. Three gaps remain:

- **Supersession is not detected.** `watch.py` sees that CAISO has posted a new TPD cycle or a new
  LCT report, and writes it to `outputs/new_documents.md`, but nothing compares the year in that
  link text against the file on disk. The download URLs are still string literals with `2025` and
  `2027` in them, so `caiso-siting download` would happily re-fetch a superseded file forever.
- **Per-figure staleness marks are not on the pages yet.** The methodology page carries the per-source
  as-of table; individual figures do not yet carry a badge when the single source behind them is
  stale.
- **PG&E's WDAT as-of is a floor, not a publication date.** It is taken from the newest request in
  the file, so the file can be newer than the date implies. It is currently STALE at 61 days
  against a monthly cadence.

## 11. Smaller items

- `LMP`/`TB4` columns are empty for all 949 nodes; `data/poi_pnodes.csv` has three rows, none
  confirmed. Nothing has been fetched yet.
- `county = "TBD"` is published verbatim for `TEMPLETON` and `EL CAPITAN`.
- `node_key` normalisation leaves voltage glued to the key on five rows, e.g.
  `INYOKERN SUBSTATION115 KV`.
- `MIRA LOMA` is labelled San Bernardino; it is in Riverside County. `LAS POSITAS` is labelled San
  Mateo; it is in Alameda County.
- The owner classifier over-blocks: some corporate names read as individuals and are counted
  rather than named. This is deliberate — when a privacy classifier must be wrong it should be
  wrong in the direction of not naming someone.
- Three rows of `data/lcr_areas.csv` are silently dropped by key normalisation
  (`Bakersfield`/`Bakersfield Junction`, `Kern PP`/`Kern Power Plant`,
  `Lambie SW Sta`/`Lambie Switching Station`), losing one bus-voltage note.

---

## Reporting a new one

Open a [data correction](https://github.com/mrk-svg/caiso-siting/issues/new?template=data-correction.yml)
with the figure, what it should say, and the public filing that shows it. See `CONTRIBUTING.md`.
