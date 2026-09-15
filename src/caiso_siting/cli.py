"""Single entry point: `caiso-siting <command>` (or `python -m caiso_siting <command>`).

  queue      parse the Public Queue Report            -> outputs/by_*.csv, projects_all.csv
  cluster15  parse the Cluster 15 report              -> outputs/cluster15_projects.csv
  nodes      unify, geocode, TPD, availability, map  -> outputs/nodes.csv, nodes_map.html, node_watch.md
  tpd        parse TPD allocation results            -> outputs/tpd_allocations.csv
  wdat       parse utility WDAT queues (PG&E)         -> outputs/wdat_projects.csv  (`wdat inspect FILE` prints headers)
  eia860     EIA-860 plants/owners/storage/LMP nodes near each node -> outputs/eia860_*.csv (data/eia860.zip)
  oasis      pnodes | suggest | fetch: OASIS day-ahead LMP TB4 -> outputs/lmp_tb4*.csv (needs internet; not in weekly)
  survival   Kaplan–Meier withdrawal survival by cluster -> outputs/survival_*.csv, survival.svg, survival.md
  snapshot   store this week's rows                   -> data/snapshots/YYYY-MM-DD/
  diff       compare the two latest snapshots         -> outputs/diff_latest.md
  parcels    parcels/zoning around a POI              -> outputs/parcels_*.csv (needs internet)
  watch      diff watched CAISO/PTO pages for new documents -> outputs/new_documents.md (needs internet)
  layers     lines | screen: CEC line placement, Williamson Act + CEC siting screens (needs internet)
  site       build the static site                    -> site/
  weekly     queue + cluster15 + nodes + survival + snapshot + diff + site, in order
  download   fetch both CAISO files (needs internet)
"""
from __future__ import annotations

import sys

from . import cluster15, diff, eia860, layers, nodes, oasis, parcels, queue_report, survival, tpd, watch, wdat
from .config import CLUSTER15_URL, DATA


def _run(mod, argv):
    saved = sys.argv
    sys.argv = [saved[0], *argv]
    try:
        mod.main()
    finally:
        sys.argv = saved


CAISO_DOCS = "https://www.caiso.com/documents/"
PGE_DOCS = "https://www.pge.com/assets/pge/docs/about/doing-business-with-pge/"

EXTRA_DOWNLOADS = {
    # required: the job fails without these two
    "cluster15.xlsx": (CLUSTER15_URL, True),
    # optional: TPD results are annual (also committed); the PG&E WDAT queue refreshes monthly
    "tpd_2025.xlsx": (CAISO_DOCS + "2025-transmission-plan-deliverability-allocation-cycle-results.xlsx", False),
    "tpd_2024.xlsx": (CAISO_DOCS + "2024-transmission-plan-deliverability-allocation-cycle-results.xlsx", False),
    "wdat_pge.xlsx": (PGE_DOCS + "PublicQueueInterconnection.xlsx", False),
    # EIA-860 bulk zip (annual, ~24 MB, public domain, no key): operating plants, owners, storage MWh, LMP nodes
    "eia860.zip": ("https://www.eia.gov/electricity/data/eia860/xls/eia8602025.zip", False),
}


def download(argv) -> None:
    import requests
    ok = queue_report.download(DATA / "publicqueuereport.xlsx")
    for name, (url, required) in EXTRA_DOWNLOADS.items():
        try:
            r = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0 (caiso-siting)"})
            r.raise_for_status()
            part = DATA / (name + ".part")
            part.write_bytes(r.content)
            # a 200 with an HTML error page, or a truncated body, must never replace a good file
            if name.endswith(".zip"):
                eia860.verify(part)
            elif name.endswith(".xlsx") and not r.content.startswith(b"PK"):
                raise ValueError("not an xlsx (no zip signature)")
            part.replace(DATA / name)
            print(f"downloaded {len(r.content):,} bytes -> {DATA / name}")
        except Exception as e:  # noqa: BLE001
            print(f"{name} download failed ({e}){' — required' if required else ' — optional, keeping existing file'}",
                  file=sys.stderr)
            ok = ok and not required
    if not ok:
        sys.exit(1)


def weekly(argv) -> None:
    from . import site
    _run(queue_report, [])
    _run(cluster15, [])
    for mod, label in ((tpd, "tpd"), (wdat, "wdat")):
        try:
            _run(mod, [])
        except SystemExit as e:  # optional inputs missing
            print(f"{label} skipped: {e}")
    _run(nodes, [])
    _run(survival, [])
    _run(diff, ["snapshot"])
    try:
        _run(diff, [])
    except SystemExit as e:  # first week: only one snapshot exists
        print(f"diff skipped: {e}")
    try:
        _run(watch, [])
    except Exception as e:  # noqa: BLE001 — network optional
        print(f"watch skipped: {e}")
    _run(site, [])


COMMANDS = {
    "queue": lambda a: _run(queue_report, a),
    "cluster15": lambda a: _run(cluster15, a),
    "nodes": lambda a: _run(nodes, a),
    "tpd": lambda a: _run(tpd, a),
    "wdat": lambda a: _run(wdat, a),
    "eia860": lambda a: _run(eia860, a),
    "watch": lambda a: _run(watch, a),
    "oasis": lambda a: _run(oasis, a),
    "survival": lambda a: _run(survival, a),
    "snapshot": lambda a: _run(diff, ["snapshot", *a]),
    "diff": lambda a: _run(diff, a),
    "parcels": lambda a: _run(parcels, a),
    "layers": lambda a: _run(layers, a),
    "site": lambda a: _run(__import__("caiso_siting.site", fromlist=["main"]), a),
    "weekly": weekly,
    "download": download,
}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in COMMANDS:
        print(__doc__)
        sys.exit(0 if argv and argv[0] in ("-h", "--help") else 2)
    COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    main()
