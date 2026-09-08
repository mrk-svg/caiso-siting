"""Single entry point: `caiso-siting <command>` (or `python -m caiso_siting <command>`).

  queue      parse the Public Queue Report            -> outputs/by_*.csv, projects_all.csv
  cluster15  parse the Cluster 15 report              -> outputs/cluster15_projects.csv
  nodes      unify, geocode, availability, map, note  -> outputs/nodes.csv, nodes_map.html, node_watch.md
  snapshot   store this week's rows                   -> data/snapshots/YYYY-MM-DD/
  diff       compare the two latest snapshots         -> outputs/diff_latest.md
  parcels    parcels/zoning around a POI              -> outputs/parcels_*.csv (needs internet)
  site       build the static site                    -> site/
  weekly     queue + cluster15 + nodes + snapshot + diff + site, in order
  download   fetch both CAISO files (needs internet)
"""
from __future__ import annotations

import sys

from . import cluster15, diff, nodes, parcels, queue_report
from .config import CLUSTER15_URL, DATA


def _run(mod, argv):
    saved = sys.argv
    sys.argv = [saved[0], *argv]
    try:
        mod.main()
    finally:
        sys.argv = saved


def download(argv) -> None:
    ok = queue_report.download(DATA / "publicqueuereport.xlsx")
    try:
        import requests
        r = requests.get(CLUSTER15_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0 (caiso-siting)"})
        r.raise_for_status()
        (DATA / "cluster15.xlsx").write_bytes(r.content)
        print(f"downloaded {len(r.content):,} bytes -> {DATA / 'cluster15.xlsx'}")
    except Exception as e:  # noqa: BLE001
        print(f"cluster15 download failed ({e})", file=sys.stderr)
        ok = False
    if not ok:
        sys.exit(1)


def weekly(argv) -> None:
    from . import site
    _run(queue_report, [])
    _run(cluster15, [])
    _run(nodes, [])
    _run(diff, ["snapshot"])
    try:
        _run(diff, [])
    except SystemExit as e:  # first week: only one snapshot exists
        print(f"diff skipped: {e}")
    _run(site, [])


COMMANDS = {
    "queue": lambda a: _run(queue_report, a),
    "cluster15": lambda a: _run(cluster15, a),
    "nodes": lambda a: _run(nodes, a),
    "snapshot": lambda a: _run(diff, ["snapshot", *a]),
    "diff": lambda a: _run(diff, a),
    "parcels": lambda a: _run(parcels, a),
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
