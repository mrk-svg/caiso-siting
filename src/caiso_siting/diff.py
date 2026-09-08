#!/usr/bin/env python3
"""
Weekly diff of the CAISO queue: what changed since the last snapshot.

    python3 diff.py snapshot      # copy data/*.xlsx + parsed CSV into data/snapshots/YYYY-MM-DD/
    python3 diff.py               # compare the two most recent snapshots -> outputs/diff_latest.md
    python3 diff.py --from 2026-09-07 --to 2026-09-14

Change classes reported (per project, keyed on queue_position + report):
  NEW            appears in the later snapshot only
  WITHDRAWN      moved from Active to Withdrawn
  COMPLETED      moved from Active to Completed
  MW_CHANGE      net_mw changed (downsizing is a common pre-withdrawal signal)
  COD_SLIP       current on-line date moved later (days)
  IA_STATUS      interconnection agreement status changed
  DELIV_CHANGE   deliverability status / TPD group changed
  POI_CHANGE     point of interconnection changed
  GONE           present before, absent now (rare; report it, don't interpret it)

This is the newsletter engine. Every line it emits traces to two CAISO rows.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from . import cluster15
from . import queue_report as caiso_queue
from .config import DATA, OUT
from .config import SNAPSHOTS as SNAP

TRACKED = ["sheet_status", "net_mw", "storage_mw", "current_cod", "ia_status", "deliverability",
           "tpd_group", "poi", "county", "utility", "project_name", "cluster", "node_key", "poi_base"]


def load_pair() -> pd.DataFrame:
    pq = caiso_queue.load_all(DATA / "publicqueuereport.xlsx")
    pq["report"] = "PUBLIC"
    frames = [pq]
    if (DATA / "cluster15.xlsx").exists():
        c15 = cluster15.load(DATA / "cluster15.xlsx")
        c15["report"] = "C15"
        frames.append(c15)
    df = pd.concat(frames, ignore_index=True, sort=False)
    for c in TRACKED:
        if c not in df:
            df[c] = pd.NA
    df["key"] = df["report"] + ":" + df["queue_position"].astype(str).str.strip()
    # a queue position can legitimately appear twice only if CAISO duplicated it; keep first
    return df.drop_duplicates("key").set_index("key")


def snapshot() -> Path:
    """Snapshot directory is named by CAISO's own 'Report Run Date' when the file carries one,
    so two runs of the same report on different days do not masquerade as two data points."""
    rows = load_pair()
    run_date = str(rows["source_run_date"].dropna().iloc[0]) if "source_run_date" in rows and rows["source_run_date"].notna().any() else ""
    d = SNAP / (run_date if run_date and run_date != "None" and run_date != "" else date.today().isoformat())
    d.mkdir(parents=True, exist_ok=True)
    for f in ("publicqueuereport.xlsx", "cluster15.xlsx"):
        if (DATA / f).exists():
            shutil.copy2(DATA / f, d / f)
    rows[TRACKED + ["report", "queue_position"]].to_csv(d / "projects.csv")
    print(f"snapshot written: {d}")
    return d


def load_snapshot(d: Path) -> pd.DataFrame:
    df = pd.read_csv(d / "projects.csv", index_col="key", dtype={"queue_position": str})
    # format="mixed": pandas otherwise infers the format from row 1 and silently NaT's the rest
    df["current_cod"] = pd.to_datetime(df["current_cod"], errors="coerce", format="mixed")
    for c in ("net_mw", "storage_mw"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def diff(a: pd.DataFrame, b: pd.DataFrame, a_name: str, b_name: str) -> tuple[pd.DataFrame, dict]:
    rows = []
    both = a.index.intersection(b.index)
    for k in b.index.difference(a.index):
        r = b.loc[k]
        rows.append(dict(key=k, change="NEW", project=r.project_name, poi=r.poi_base, county=r.county,
                         mw=r.net_mw, detail=f"{r.sheet_status} {r.cluster}"))
    for k in a.index.difference(b.index):
        r = a.loc[k]
        rows.append(dict(key=k, change="GONE", project=r.project_name, poi=r.poi_base, county=r.county,
                         mw=r.net_mw, detail=f"was {r.sheet_status}"))
    for k in both:
        x, y = a.loc[k], b.loc[k]
        base = dict(key=k, project=y.project_name, poi=y.poi_base, county=y.county, mw=y.net_mw)
        if x.sheet_status != y.sheet_status:
            rows.append({**base, "change": y.sheet_status if y.sheet_status in ("WITHDRAWN", "COMPLETED") else "STATUS",
                         "detail": f"{x.sheet_status} -> {y.sheet_status}"})
        if pd.notna(x.net_mw) and pd.notna(y.net_mw) and abs(x.net_mw - y.net_mw) > 0.5:
            rows.append({**base, "change": "MW_CHANGE", "detail": f"{x.net_mw:,.0f} -> {y.net_mw:,.0f} MW"})
        if pd.notna(x.current_cod) and pd.notna(y.current_cod) and y.current_cod != x.current_cod:
            days = (y.current_cod - x.current_cod).days
            rows.append({**base, "change": "COD_SLIP" if days > 0 else "COD_PULLED_IN",
                         "detail": f"{x.current_cod:%Y-%m-%d} -> {y.current_cod:%Y-%m-%d} ({days:+d} d)"})
        for col, label in (("ia_status", "IA_STATUS"), ("deliverability", "DELIV_CHANGE"),
                           ("tpd_group", "DELIV_CHANGE"), ("poi", "POI_CHANGE")):
            xv, yv = str(x[col]) if pd.notna(x[col]) else "", str(y[col]) if pd.notna(y[col]) else ""
            if xv != yv:
                rows.append({**base, "change": label, "detail": f"{col}: {xv or '—'} -> {yv or '—'}"})
    changes = pd.DataFrame(rows, columns=["key", "change", "project", "poi", "county", "mw", "detail"])

    def totals(df):
        act = df[df.sheet_status == "ACTIVE"]
        return dict(active_n=len(act), active_mw=act.net_mw.sum(), active_storage_mw=act.storage_mw.sum(),
                    c15_active_n=len(act[act.report == "C15"]), c15_active_mw=act[act.report == "C15"].net_mw.sum(),
                    withdrawn_n=(df.sheet_status == "WITHDRAWN").sum())
    return changes, {a_name: totals(a), b_name: totals(b)}


def write_report(changes: pd.DataFrame, tots: dict, a_name: str, b_name: str) -> None:
    ta, tb = tots[a_name], tots[b_name]
    by_node = (changes[changes.change.isin(["WITHDRAWN", "MW_CHANGE", "COD_SLIP", "NEW"])]
               .groupby(["poi", "change"]).mw.agg(["count", "sum"]).round(0)
               .sort_values("sum", ascending=False).head(15))
    md = [f"# CAISO queue diff — {a_name} → {b_name}", "",
          "| | " + a_name + " | " + b_name + " | Δ |", "|---|---:|---:|---:|"]
    for k, lbl in (("active_n", "Active projects"), ("active_mw", "Active MW"), ("active_storage_mw", "Active storage MW"),
                   ("c15_active_n", "Cluster 15 active projects"), ("c15_active_mw", "Cluster 15 active MW"),
                   ("withdrawn_n", "Withdrawn projects (cumulative)")):
        md.append(f"| {lbl} | {ta[k]:,.0f} | {tb[k]:,.0f} | {tb[k]-ta[k]:+,.0f} |")
    md += ["", f"## Changes ({len(changes)})", ""]
    if changes.empty:
        md.append("No row-level changes between snapshots.")
    else:
        md.append(changes.change.value_counts().rename_axis("change").reset_index(name="n").to_markdown(index=False))
        md += ["", "## By node (withdrawals, resizes, COD slips, new requests)", "",
               by_node.reset_index().to_markdown(index=False) if len(by_node) else "—",
               "", "## Every change", ""]
        show = changes.sort_values(["change", "mw"], ascending=[True, False]).copy()
        show["mw"] = show.mw.round(0)
        md.append(show[["change", "project", "poi", "county", "mw", "detail"]].to_markdown(index=False))
    md += ["", "_Every line above is the difference between two CAISO rows. No reason is stated because CAISO states none._"]
    (OUT / "diff_latest.md").write_text("\n".join(md))
    changes.to_csv(OUT / "diff_latest.csv", index=False)
    print(f"{len(changes)} changes; wrote outputs/diff_latest.md")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["snapshot", "diff"], default="diff")
    ap.add_argument("--from", dest="a")
    ap.add_argument("--to", dest="b")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.cmd == "snapshot":
        snapshot()
        return
    snaps = sorted(p for p in SNAP.glob("????-??-??") if (p / "projects.csv").exists())
    if args.a and args.b:
        a, b = SNAP / args.a, SNAP / args.b
    elif len(snaps) >= 2:
        a, b = snaps[-2], snaps[-1]
    else:
        sys.exit(f"need two snapshots in {SNAP}/ (have {len(snaps)}); run `python3 diff.py snapshot` after each download")
    changes, tots = diff(load_snapshot(a), load_snapshot(b), a.name, b.name)
    write_report(changes, tots, a.name, b.name)


if __name__ == "__main__":
    main()
