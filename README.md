# caiso-siting

Free-data pipeline for CAISO interconnection node intelligence. Target user: small/mid
BESS developers and land brokers in the CAISO footprint who can't afford LandGate or Nira.

Not a "Grid-Ready Score". Transparent, sourced layers — every number traceable to a CAISO row.

## Layout

    caiso_queue.py       Public Queue Report parser (Cluster 14 and earlier + completed + withdrawn)
    cluster15.py         Cluster 15 report parser (different schema, dirty county names — normalized)
    nodes.py             unify both per node, geocode vs OpenStreetMap, emit map + node_watch.md
    data/                raw downloads (gitignored) + poi_overrides.csv (hand-verified coordinates)
    outputs/             CSVs, nodes_map.html, node_watch.md

## Run (weekly)

    # 1. refresh the two CAISO files (browser download if your network blocks caiso.com)
    #    https://www.caiso.com/documents/publicqueuereport.xlsx              -> data/publicqueuereport.xlsx
    #    https://www.caiso.com/documents/cluster-15-interconnection-requests.xlsx -> data/cluster15.xlsx
    # 2. refresh substations (only occasionally; OSM changes slowly) — see "Substation coordinates"
    pip install -r requirements.txt
    python3 caiso_queue.py
    python3 cluster15.py
    python3 nodes.py
    open outputs/nodes_map.html

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
- Fill `data/poi_overrides.csv` for the unmatched heavy nodes (Trout Canyon, Dry Lake, Manning, Moss Landing,
  Tranquility, Hoodoo Wash, Harlan, Cielo Azul, Arco, Calcite, Delaney, Gamebird). Cite the source in `note`.

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
