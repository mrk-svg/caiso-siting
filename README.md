# caiso-siting

Free-data pipeline for CAISO interconnection node intelligence. Target user: small/mid
BESS developers and land brokers in the CAISO footprint who can't afford LandGate or Nira.

Not a "Grid-Ready Score". Transparent, sourced layers — every number traceable to a CAISO row.

## Install

    pip install -e .[dev]          # Python 3.10+; pandas, openpyxl, requests, tabulate
    caiso-siting --help
    python -m pytest -q            # 137 tests, ~15 s

## Layout

    src/caiso_siting/
      config.py          paths (CAISO_SITING_ROOT or nearest parent with data/), provenance stamps
      common.py          shared normalizers: county cleanup, POI node key, line-endpoint split
      queue_report.py    Public Queue Report parser (Cluster 14 and earlier + completed + withdrawn)
      cluster15.py       Cluster 15 report parser (different schema)
      nodes.py           unify per node, geocode, county-centroid fallback, POI availability, map, node_watch.md
      diff.py            weekly snapshot + diff -> outputs/diff_latest.md (the newsletter engine)
      parcels.py         parcels / zoning / general plan within N km of a POI (public county ArcGIS)
      site.py            static site -> site/ (index, map, per-node pages, diff, note) for GitHub Pages
      cli.py             `caiso-siting` entry point
    tests/               pytest suite (synthetic CAISO-layout fixtures + real-file smoke tests + header-drift guard)
    data/                raw downloads (gitignored), osm_substations.csv (committed, ODbL), poi_overrides.csv,
                         poi_availability.csv, snapshots/YYYY-MM-DD/projects.csv
    outputs/             CSVs, nodes_map.html, node_watch.md, diff_latest.md
    site/                generated static site
    .github/workflows/   ci.yml (ruff + pytest), weekly.yml (Monday cron: download, run, snapshot, deploy, diff issue)
    DATA.md              data dictionary — every column, unit, source, caveat
    DATA_LICENSES.md     source terms and the attribution each output must carry

## Metrics — which one you may quote (full definitions in DATA.md)

| metric            | definition                                                            | quote it? |
|-------------------|-----------------------------------------------------------------------|-----------|
| `storage_churn`   | storage MW withdrawn in last 5 yrs ÷ (active + operating storage MW)  | yes       |
| `wd_post_phase2_mw` | MW that withdrew after Phase II / FAS results were in hand           | yes, as a stage signal, never as a cause |
| `c15_survival`    | C15 active ÷ (C15 active + C15 withdrawn)                             | yes       |
| `churn_alltime`   | all withdrawn MW since 2006 ÷ surviving MW                            | historical color only — it mostly counts dead 2008–2015 wind/solar |

Why this matters: Whirlwind reads 1.32 all-time (looks like a graveyard) but 0.25 storage churn with 2.1 GW operating.
Colorado River reads 2.11 all-time and 0.14 on storage. Red Bluff (1.62), Lugo (2.18) and Los Banos (1.30) are bad on both.
The CAISO files contain no withdrawal reason beyond "IC Request"; never state a cause.

## Run (weekly — this is the whole newsletter workflow)

    # 1. refresh the two CAISO files (browser download if your network blocks caiso.com)
    #    https://www.caiso.com/documents/publicqueuereport.xlsx              -> data/publicqueuereport.xlsx
    #    https://www.caiso.com/documents/cluster-15-interconnection-requests.xlsx -> data/cluster15.xlsx
    # 2. refresh substations only occasionally (OSM changes slowly) — see "Substation coordinates"
    caiso-siting download            # both CAISO files (needs normal internet)
    caiso-siting weekly              # = queue, cluster15, nodes, snapshot, diff, site — in order
    open site/index.html

    # or step by step
    caiso-siting queue | cluster15 | nodes | snapshot | diff | site

On GitHub the same thing runs every Monday 14:00 UTC via `.github/workflows/weekly.yml`, commits the snapshot and
site, deploys Pages, and opens an issue titled "Weekly diff <date>". Set the repo's Pages source to "GitHub Actions" once.

Snapshot zero is 2026-09-07. The first real diff exists after the second weekly download.
`diff.py` reports NEW, WITHDRAWN, COMPLETED, MW_CHANGE, COD_SLIP / COD_PULLED_IN, IA_STATUS, DELIV_CHANGE, POI_CHANGE, GONE —
each as the difference between two CAISO rows. Self-tested against a mutated snapshot (all classes fire).

## Parcels around a stated-available POI

    caiso-siting parcels "DRY LAKE SW STA" --km 5    # needs normal internet
    caiso-siting parcels --all-available --km 5

Public layers wired in (verified live 2026-09-07): Kings County parcels + general plan; Kern County zoning.
Live check: 40 Kings parcels within 5 km of the proposed Dry Lake 500 kV station, all agricultural, 160–320-acre sections;
Kern zoning around Bitterwater returns Exclusive Agriculture plus a "South Kern Industrial Specific Plan" polygon.
Not public: Kern countywide parcels (the Assessor sells them), Fresno County parcel REST (not found). Ownership is redacted
by statute in every California county layer — parcel + APN is what you get; owner lookup is the broker's job.

## What the data says (2026-09-07 run)

| Cohort                         | Projects | Net MW  | Storage MW |
|--------------------------------|---------:|--------:|-----------:|
| Legacy active (C14 and prior)  |     266  |  74,687 |  64,972 |
| Legacy completed               |     252  |  35,593 |  11,720 |
| Legacy withdrawn (all-time)    |   1,763  | 381,917 | 134,722 |
| Cluster 15 active              |      86  |  28,449 |  22,005 |
| Cluster 15 withdrawn           |      84  |  30,564 |     —   |

- 92% of legacy active projects and 77% of Cluster 15 include a battery.
- 214 of 266 legacy active projects already hold an executed IA — the public queue report
  is the late-stage pipeline. Cluster 15 is the pipeline that matters for new entrants.
- Cluster 15 has shed ~58% of its MW since CAISO's July 2025 briefing (145 projects / ~68 GW → 86 / 28 GW).
  Withdrawal waves: Apr–May 2025, Nov–Dec 2025, Jun–Jul 2026.
- Biggest nodes by combined pipeline: Windhub (4.6 GW; 11 GW withdrawn behind it), Red Bluff (3.6 GW; 10.5 GW withdrawn),
  Vincent (3.5 GW), Whirlwind (3.3 GW), Delaney–Colorado River (3.2 GW), Trout Canyon (3.0 GW), Dry Lake (2.95 GW, all C15).
- Churn ratio (withdrawn ÷ surviving MW) > 2 at Red Bluff, Lugo, Colorado River: graveyard nodes.

## Substation coordinates (the hard part the pitch hand-waved)

- HIFLD substations: now "restricted public" on data.gov.
- CEC "California Electric Substations" ArcGIS layer: now returns `Token Required`.
- What works free: OpenStreetMap via Overpass (ODbL). Query used (bbox covers CA + NV/AZ POIs):

      [out:csv(::id,::type,::lat,::lon,name,voltage,operator,substation;true;",")][timeout:150];
      (nwr["power"="substation"][name](32.3,-124.6,42.2,-113.8););
      out center;

  Save the response as `data/osm_substations.csv`. Only ~1,370 named substations exist in that box,
  so coverage is incomplete: current match is ~52% of nodes / ~69% of pipeline MW.
- `outputs/poi_geocode.csv` lists every POI, the OSM feature it matched, the score and method
  (`exact`, `fuzzy`, `line-midpoint`, `line-one-end`, `override`, `none`). Audit anything not `exact`.
- `data/poi_overrides.csv` carries Dry Lake, Harlan, Bitterwater (CAISO notice coordinates), Moss Landing and Gamebird
  (OSM ways, cited), and Tranquility as `approx=yes` (plant centroid). Coverage: 78% of pipeline MW, 39 of the top 50 nodes.
  Still unlocated after an OSM name/ref/description search: Trout Canyon, Manning, East County (Baja), Hoodoo Wash, Cielo Azul,
  Arco, Calcite, Delaney, Hassayampa — and the second endpoint of every `line-one-end` row.
- `line-one-end` markers sit at one end of a transmission line, not at the tap. The map draws them dashed and pale;
  `node_watch.md` lists every >500 MW node whose position is approximate or missing.

## Official POI-availability layer

CAISO and the PTOs publish prose notices saying which POIs can or cannot take Cluster 16 requests (short-circuit duty,
terminal space, unsponsored lines, new switching stations). No spreadsheet tool ingests these. `data/poi_availability.csv`
encodes them one row per POI per source, with status AVAILABLE / UNAVAILABLE / CONDITIONAL / RELIEVED and the source URL.
Rule: only encode a POI a source names. Add a row every time a new notice appears; the latest date wins in the join.

## Known limitations

1. `net_mw` is net-to-grid; component MW can exceed it for hybrids, so storage_mw > net_mw is expected.
2. Cluster 15 deliverability is *requested*, not allocated. TPD allocation is a separate CAISO process.
3. Withdrawal ≠ failure of the node; developers withdraw for portfolio reasons.
4. Nothing here is load-side. Data center load interconnection has no public queue.
5. County strings in the C15 file are hand-typed ("king", "San Bernadino", "Kings and Fresno"). Partially fixed in `cluster15.py`.

## Next layers, in the order that changes decisions

1. CAISO TPD allocation reports + constraint-mapping workbook (decides who gets deliverability) — join to nodes.
2. Week-over-week diff of both CAISO files (new withdrawals, COD slips, IA status changes) — the newsletter engine.
3. OASIS nodal LMP history for the ~40 nodes that matter, not the whole grid.
4. Only then: a UI.
