#!/usr/bin/env python3
"""
CAISO Generator Interconnection Queue — parser & aggregator.

Reads CAISO's Public Queue Report (publicqueuereport.xlsx), normalizes the
three sheets (Active / Completed / Withdrawn), and writes aggregate CSVs:

  outputs/projects_all.csv          one clean row per project, all three sheets
  outputs/by_county.csv             active vs withdrawn counts/MW per county
  outputs/by_poi.csv                per Point of Interconnection (substation/line)
  outputs/by_cluster.csv            per study process / cluster
  outputs/withdrawals_by_year.csv   withdrawal volume over time
  outputs/deliverability.csv        active MW by deliverability status & TPD group

Usage:
  python caiso_queue.py                      # uses data/publicqueuereport.xlsx
  python caiso_queue.py --file path.xlsx
  python caiso_queue.py --download           # tries to fetch the live report first

Only pandas + openpyxl (+ requests for --download) are required.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from .common import clean_county, norm_poi, poi_base
from .config import DATA, OUT, PUBLIC_QUEUE_URL, add_provenance, xlsx_run_date

QUEUE_URL = PUBLIC_QUEUE_URL
HEADER_ROW = 3  # 0-indexed: row 4 in Excel holds the column names on every sheet

SHEETS = {
    "Grid GenerationQueue": "ACTIVE",
    "Completed Generation Projects": "COMPLETED",
    "Withdrawn Generation Projects": "WITHDRAWN",
}

# Raw header (after whitespace collapse) -> canonical snake_case name.
# Anything not listed is auto-snake_cased.
RENAME = {
    "Project Name": "project_name",
    "Project Name - Confidential": "project_name",
    "Queue Position": "queue_position",
    "Interconnection Request Receive Date": "request_received",
    "Queue Date": "queue_date",
    "Application Status": "status",
    "Withdrawn Date": "withdrawn_date",
    "Study Process": "study_process",
    "Type-1": "type_1", "Type-2": "type_2", "Type-3": "type_3",
    "Fuel-1": "fuel_1", "Fuel-2": "fuel_2", "Fuel-3": "fuel_3",
    "MW-1": "mw_1", "MW-2": "mw_2", "MW-3": "mw_3",
    "Net MWs to Grid": "net_mw",
    "Full Capacity, Partial or Energy Only (FC/P/EO)": "deliverability",
    "TPD Allocation Percentage": "tpd_pct",
    "Off-Peak Deliverability and Economic Only": "offpeak_deliverability",
    "TPD Allocation Group": "tpd_group",
    "County": "county",
    "State": "state",
    "Utility": "utility",
    "PTO Study Region": "pto_region",
    "Station or Transmission Line": "poi",
    "Proposed On-line Date (as filed with IR)": "proposed_cod",
    "Current On-line Date": "current_cod",
    "Actual On-line Date": "actual_cod",
    "Suspension Status": "suspension_status",
    "Feasibility Study or Supplemental Review": "study_feasibility",
    "System Impact Study or Phase I Cluster Study": "study_sis_phase1",
    "Facilities Study (FAS) or Phase II Cluster Study": "study_fas_phase2",
    "Optional Study (OS)": "study_optional",
    "Interconnection Agreement Status": "ia_status",
    "Reason for Withdrawal": "withdrawal_reason",
}


def _clean_header(h) -> str:
    if h is None or (isinstance(h, float) and pd.isna(h)):
        return ""
    return re.sub(r"\s+", " ", str(h)).strip()


def _snake(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")


def load_sheet(path: Path, sheet: str, status_label: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=HEADER_ROW, dtype=str)
    cols = []
    for c in raw.columns:
        h = _clean_header(c)
        if not h or h.startswith("Unnamed"):
            cols.append(None)
            continue
        # prefix-match so minor wording drift in CAISO's headers still maps
        canon = RENAME.get(h)
        if canon is None:
            for k, v in RENAME.items():
                if h.startswith(k[:20]):
                    canon = v
                    break
        cols.append(canon or _snake(h))
    raw.columns = [c if c else f"_drop_{i}" for i, c in enumerate(cols)]
    df = raw[[c for c in raw.columns if not c.startswith("_drop_")]].copy()
    df = df.dropna(how="all")
    # kill footer/blank rows: CAISO appends a disclaimer sentence in the project-name column
    df = df[df["project_name"].notna() & df["queue_position"].notna()]
    df["sheet_status"] = status_label
    return df


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("mw_1", "mw_2", "mw_3", "net_mw", "tpd_pct"):
        if c in df:
            df[c] = pd.to_numeric(df[c].str.replace(",", ""), errors="coerce")
    for c in ("request_received", "queue_date", "withdrawn_date",
              "proposed_cod", "current_cod", "actual_cod"):
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    for c in ("poi", "utility", "study_process", "deliverability",
              "tpd_group", "pto_region", "status"):
        if c in df:
            df[c] = df[c].fillna("").str.strip().str.upper()
    df["county"] = clean_county(df["county"])

    # Technology flags
    types = df[[c for c in ("type_1", "type_2", "type_3") if c in df]].fillna("")
    fuels = df[[c for c in ("fuel_1", "fuel_2", "fuel_3") if c in df]].fillna("")
    blob = (types.agg(" ".join, axis=1) + " " + fuels.agg(" ".join, axis=1)).str.upper()
    df["has_storage"] = blob.str.contains("STORAGE|BATTERY")
    df["has_solar"] = blob.str.contains("SOLAR|PHOTOVOLTAIC")
    df["has_wind"] = blob.str.contains("WIND")
    df["is_standalone_storage"] = df["has_storage"] & ~df["has_solar"] & ~df["has_wind"] \
        & ~blob.str.contains("GAS|COMBUSTION|COMBINED|GEOTHERMAL|HYDRO|BIOMASS")

    # Storage MW: MW-n where the matching Type-n/Fuel-n is storage
    storage_mw = pd.Series(0.0, index=df.index)
    for n in (1, 2, 3):
        t, f, m = f"type_{n}", f"fuel_{n}", f"mw_{n}"
        if m in df:
            is_stor = df.get(t, "").fillna("").str.upper().str.contains("STORAGE") | \
                      df.get(f, "").fillna("").str.upper().str.contains("BATTERY")
            storage_mw += df[m].fillna(0).where(is_stor, 0)
    df["storage_mw"] = storage_mw

    # Cluster label from study process ("Cluster 14", "Cluster 15", "Serial LGIP", ...)
    df["cluster"] = df["study_process"].str.extract(r"(CLUSTER\s*\d+)", expand=False) \
        .fillna(df["study_process"])
    df["queue_year"] = df["queue_date"].dt.year
    if "withdrawn_date" in df:
        df["withdrawn_year"] = df["withdrawn_date"].dt.year

    # Withdrew after Phase II / Facilities Study results were in hand. Not a cause,
    # but the only stage signal the file offers.
    df["withdrew_post_phase2"] = (df["sheet_status"] == "WITHDRAWN") & \
        (df.get("study_fas_phase2", pd.Series("", index=df.index)).fillna("").str.upper() == "COMPLETE")

    # MW at the point of interconnection. The public report's "Net MWs to Grid" is the POI figure;
    # component MW (mw_1..3) can exceed it for hybrids. Use poi_mw wherever "capacity" is meant.
    df["poi_mw"] = df["net_mw"]

    df["poi_base"] = poi_base(df["poi"])      # display label
    df["node_key"] = df["poi"].map(norm_poi)  # join key shared with cluster15.py
    return df


def load_all(path: Path | None = None) -> pd.DataFrame:
    path = Path(path) if path else DATA / "publicqueuereport.xlsx"
    frames = [normalize(load_sheet(path, s, lbl)) for s, lbl in SHEETS.items()]
    df = pd.concat(frames, ignore_index=True, sort=False)
    return add_provenance(df, path.name, xlsx_run_date(path))


# ---------------------------------------------------------------- aggregates

def by_county(df: pd.DataFrame) -> pd.DataFrame:
    def agg(sub, prefix):
        g = sub.groupby("county").agg(
            **{f"{prefix}_projects": ("project_name", "count"),
               f"{prefix}_mw": ("net_mw", "sum"),
               f"{prefix}_storage_mw": ("storage_mw", "sum")})
        return g
    act = agg(df[df.sheet_status == "ACTIVE"], "active")
    wd = agg(df[df.sheet_status == "WITHDRAWN"], "withdrawn")
    done = agg(df[df.sheet_status == "COMPLETED"], "completed")
    out = act.join(wd, how="outer").join(done, how="outer").fillna(0)
    out["withdrawal_rate_by_count"] = (
        out["withdrawn_projects"] /
        (out["withdrawn_projects"] + out["active_projects"] + out["completed_projects"]).replace(0, float("nan"))
    ).astype(float).round(3)
    out["withdrawal_rate_by_mw"] = (
        out["withdrawn_mw"] /
        (out["withdrawn_mw"] + out["active_mw"] + out["completed_mw"]).replace(0, float("nan"))
    ).astype(float).round(3)
    return out.sort_values("active_mw", ascending=False).round(1)


def by_poi(df: pd.DataFrame) -> pd.DataFrame:
    act = df[df.sheet_status == "ACTIVE"].groupby(["poi_base", "county", "utility"]).agg(
        active_projects=("project_name", "count"),
        active_mw=("net_mw", "sum"),
        active_storage_mw=("storage_mw", "sum"),
        full_capacity_mw=("net_mw", lambda s: s[df.loc[s.index, "deliverability"]
                                                .str.startswith("FULL")].sum()),
        energy_only_mw=("net_mw", lambda s: s[df.loc[s.index, "deliverability"]
                                              .str.startswith("ENERGY")].sum()),
    )
    wd = df[df.sheet_status == "WITHDRAWN"].groupby(["poi_base", "county", "utility"]).agg(
        withdrawn_projects=("project_name", "count"),
        withdrawn_mw=("net_mw", "sum"),
    )
    done = df[df.sheet_status == "COMPLETED"].groupby(["poi_base", "county", "utility"]).agg(
        completed_mw=("net_mw", "sum"))
    out = act.join(wd, how="outer").join(done, how="outer").fillna(0)
    out["churn_ratio"] = (out["withdrawn_mw"] / (out["active_mw"] + out["completed_mw"]).replace(0, float("nan"))) \
        .astype(float).round(2)
    return out.reset_index().sort_values("active_mw", ascending=False).round(1)


def by_cluster(df: pd.DataFrame) -> pd.DataFrame:
    return (df.pivot_table(index="cluster", columns="sheet_status", values="net_mw",
                           aggfunc=["count", "sum"], fill_value=0)
            .round(0))


def withdrawals_by_year(df: pd.DataFrame) -> pd.DataFrame:
    wd = df[(df.sheet_status == "WITHDRAWN") & df["withdrawn_year"].notna()]
    return wd.groupby(wd["withdrawn_year"].astype(int)).agg(
        withdrawn_projects=("project_name", "count"),
        withdrawn_mw=("net_mw", "sum"),
        withdrawn_storage_mw=("storage_mw", "sum")).round(0)


def deliverability(df: pd.DataFrame) -> pd.DataFrame:
    act = df[df.sheet_status == "ACTIVE"]
    return act.pivot_table(index="deliverability", columns="tpd_group", values="net_mw",
                           aggfunc="sum", fill_value=0, margins=True).round(0)


# --------------------------------------------------------------------- main

def download(dest: Path) -> bool:
    try:
        import requests
        r = requests.get(QUEUE_URL, timeout=60,
                         headers={"User-Agent": "Mozilla/5.0 (queue-parser)"})
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        print(f"downloaded {len(r.content):,} bytes -> {dest}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"download failed ({e}); falling back to local file", file=sys.stderr)
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=str(DATA / "publicqueuereport.xlsx"))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()

    path = Path(args.file)
    if args.download:
        download(path)
    if not path.exists():
        sys.exit(f"missing {path} — download {QUEUE_URL} into it (or pass --download)")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df = load_all(path)
    df.to_csv(out / "projects_all.csv", index=False)
    county = by_county(df)
    county.to_csv(out / "by_county.csv")
    poi = by_poi(df)
    poi.to_csv(out / "by_poi.csv", index=False)
    clus = by_cluster(df)
    clus.to_csv(out / "by_cluster.csv")
    wby = withdrawals_by_year(df)
    wby.to_csv(out / "withdrawals_by_year.csv")
    deliv = deliverability(df)
    deliv.to_csv(out / "deliverability.csv")

    pd.set_option("display.width", 160, "display.max_columns", 20)
    act = df[df.sheet_status == "ACTIVE"]
    print(f"\nCAISO Public Queue Report  ({path.name})")
    print("=" * 70)
    for lbl in ("ACTIVE", "COMPLETED", "WITHDRAWN"):
        s = df[df.sheet_status == lbl]
        print(f"{lbl:<10} {len(s):>5} projects  {s.net_mw.sum():>10,.0f} MW  "
              f"(storage {s.storage_mw.sum():>9,.0f} MW)")
    print(f"\nActive projects with storage: {act.has_storage.sum()} "
          f"({act.has_storage.mean():.0%});  standalone storage: {act.is_standalone_storage.sum()}")

    print("\nTop 15 counties by ACTIVE MW")
    print(county.head(15)[["active_projects", "active_mw", "active_storage_mw",
                           "withdrawn_projects", "withdrawn_mw", "withdrawal_rate_by_mw"]])
    print("\nTop 15 POIs by ACTIVE MW (the 'clogged' nodes)")
    print(poi.head(15)[["poi_base", "county", "utility", "active_projects", "active_mw",
                        "withdrawn_mw", "churn_ratio"]].to_string(index=False))
    print("\nActive MW by deliverability status x TPD group")
    print(deliv)
    print("\nWithdrawals by year (last 10)")
    print(wby.tail(10))
    print("\nBy cluster / study process")
    print(clus)
    print(f"\nCSV outputs written to {out.resolve()}/")


if __name__ == "__main__":
    main()
