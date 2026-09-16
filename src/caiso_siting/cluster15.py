#!/usr/bin/env python3
"""
CAISO Cluster 15 queue report parser.

Source: https://www.caiso.com/documents/cluster-15-interconnection-requests.xlsx
Two sheets ("Cluster 15", "Withdrawn") with a different schema from the
Public Queue Report. This module normalizes it to the same column names used
by caiso_queue.py so the two can be concatenated.

    python cluster15.py                  # reads data/cluster15.xlsx, writes outputs/cluster15_projects.csv
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from .common import cap_storage_mw, clean_county, norm_poi, poi_base, tech_flags
from .config import CLUSTER15_URL, DATA, OUT, add_provenance, csv_safe

C15_URL = CLUSTER15_URL

RENAME = {
    "Queue Number": "queue_position",
    "Project Number": "project_number",
    "Project Name": "project_name",
    "Generation/Fuel 1": "fuel_1", "NET MW 1": "mw_1",
    "Generation/Fuel 2": "fuel_2", "NET MW 2": "mw_2",
    "Generation/Fuel 3": "fuel_3", "NET MW 3": "mw_3",
    "NET MW POI": "net_mw",
    "PROJECT COUNTY": "county",
    "Project State": "state",
    "Study Area": "study_area",
    "PTO": "utility",
    "POI": "poi",
    "Voltage kV": "poi_kv",
    "Requested COD": "proposed_cod",
    "Queue Date": "queue_date",
    "Application Date": "request_received",
    "Withdrawal Date": "withdrawn_date",
    "Service Type": "service_type",
}

def load(path: Path | None = None) -> pd.DataFrame:
    path = Path(path) if path else DATA / "cluster15.xlsx"
    frames = []
    xls = pd.ExcelFile(path)
    names = {n.strip().upper(): n for n in xls.sheet_names}  # CAISO leaves trailing spaces
    for key, label in (("CLUSTER 15", "ACTIVE"), ("WITHDRAWN", "WITHDRAWN")):
        sheet = next((v for k, v in names.items() if k.startswith(key)), None)
        if sheet is None:
            sys.exit(f"sheet starting with '{key}' not found; sheets are {xls.sheet_names}")
        raw = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        raw.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in raw.columns]
        df = raw.rename(columns=RENAME)
        df = df[df["project_name"].notna()].copy()
        df["sheet_status"] = label
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    for c in ("mw_1", "mw_2", "mw_3", "net_mw", "poi_kv"):
        df[c] = pd.to_numeric(df[c].replace("N/A", None), errors="coerce")
    for c in ("proposed_cod", "queue_date", "request_received", "withdrawn_date"):
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    df["county"] = clean_county(df["county"])
    for c in ("state", "utility", "poi", "study_area", "service_type"):
        df[c] = df[c].fillna("").str.strip().str.upper()

    fuels = df[["fuel_1", "fuel_2", "fuel_3"]].fillna("").agg(" ".join, axis=1).str.upper()
    for c, v in tech_flags(fuels).items():
        df[c] = v

    storage_mw = pd.Series(0.0, index=df.index)
    for n in (1, 2, 3):
        is_stor = df[f"fuel_{n}"].fillna("").str.upper().str.contains("STORAGE|BATTERY")
        storage_mw += df[f"mw_{n}"].fillna(0).where(is_stor, 0)
    df["storage_component_mw"] = storage_mw
    df["storage_mw"] = cap_storage_mw(storage_mw, df["net_mw"])

    # Deliverability requested (C15 asks for it; nothing is allocated yet)
    st = df["service_type"]
    df["deliverability"] = pd.Series("", index=df.index) \
        .mask(st.str.contains("ENERGY ONLY"), "ENERGY ONLY (REQ)") \
        .mask(st.str.contains("FULL CAPACITY"), "FULL CAPACITY (REQ)")
    df["is_merchant"] = st.str.contains("MERCHANT")

    df["cluster"] = "C15"
    df["study_process"] = "C15"
    df["queue_year"] = df["queue_date"].dt.year
    df["withdrawn_year"] = df["withdrawn_date"].dt.year if "withdrawn_date" in df else pd.NA
    df["withdrew_post_phase2"] = False   # C15 Phase I results only landed mid-2026; no Phase II yet
    df["poi_mw"] = df["net_mw"]               # "NET MW POI" in CAISO's C15 schema
    df["poi_base"] = poi_base(df["poi"])
    df["node_key"] = df["poi"].map(norm_poi)
    return add_provenance(df, path.name, None)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "cluster15.xlsx"
    if not path.exists():
        sys.exit(f"missing {path} — download {C15_URL}")
    df = load(path)
    OUT.mkdir(exist_ok=True)
    csv_safe(df).to_csv(OUT / "cluster15_projects.csv", index=False)

    a = df[df.sheet_status == "ACTIVE"]
    w = df[df.sheet_status == "WITHDRAWN"]
    print(f"Cluster 15: {len(a)} active ({a.net_mw.sum():,.0f} MW, storage {a.storage_mw.sum():,.0f} MW) | "
          f"{len(w)} withdrawn ({w.net_mw.sum():,.0f} MW)")
    print(f"Active with storage: {a.has_storage.mean():.0%} | standalone storage: {a.is_standalone_storage.sum()}")
    print("\nActive MW by requested service type:")
    print(a.groupby("service_type").net_mw.agg(["count", "sum"]).round(0))
    print("\nActive MW by study area:")
    print(a.groupby("study_area").net_mw.agg(["count", "sum"]).sort_values("sum", ascending=False).round(0))
    print("\nTop 15 C15 POIs by active MW:")
    print(a.groupby(["poi_base", "county", "utility"]).net_mw.agg(["count", "sum"])
           .sort_values("sum", ascending=False).head(15).round(0))
    print("\nWithdrawals by month:")
    print(w.groupby(w.withdrawn_date.dt.to_period("M")).net_mw.agg(["count", "sum"]).round(0))


if __name__ == "__main__":
    main()
