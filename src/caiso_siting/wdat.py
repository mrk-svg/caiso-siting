"""
Wholesale Distribution Access Tariff (WDAT) queues — the distribution-level door into the grid.

Built against PG&E's public queue (verified 2026-09-08):
  data/wdat_pge.xlsx   https://www.pge.com/assets/pge/docs/about/doing-business-with-pge/PublicQueueInterconnection.xlsx
  sheet "Public Queue", title rows then a numbered row, header on row 4; 4,659 rows; queue numbers "0001-WD";
  status Active / In Service / Withdrawn; process Fast Track / Detailed Study / Independent Study / DGSP / Cluster;
  Substation is free text ("WILLOW PASS SUB"); Summer Max Capacity (MW).
SCE and SDG&E: SCE's queue is a SharePoint link on sce.com, SDG&E's is on sdge.com; drop them in as
data/wdat_sce.xlsx / data/wdat_sdge.xlsx and add a column map in MAPS (run `caiso-siting wdat inspect FILE`
to print the headers). Nothing is guessed: an unmapped utility is skipped with a message.

Per-node columns added to nodes.csv (node_key = norm_poi(Substation), so a WDAT substation that is also a
CAISO POI lands on the same node):
  wdat_active_projects, wdat_active_mw, wdat_active_storage_mw, wdat_inservice_mw, wdat_withdrawn_mw

WDAT queue numbers ("2179-WD") are the ids the TPD allocation files use for distribution-level requests,
so outputs/tpd_allocations.csv rows with in_generator_queue == False join to outputs/wdat_projects.csv on queue_position.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from .common import clean_county, norm_poi, poi_base
from .config import DATA, OUT, add_provenance

FILES = {"PGAE": "wdat_pge.xlsx", "SCE": "wdat_sce.xlsx", "SDGE": "wdat_sdge.xlsx"}

# canonical -> list of header substrings (lower-case) to match, per utility
MAPS = {
    "PGAE": {
        "request_received": ["date interconnection request received"],
        "queue_position": ["queue number"],
        "process_applied": ["process type applied"],
        "process": ["current process type"],
        "status": ["current interconnection request status"],
        "proposed_cod": ["customer requested cod"],
        "current_cod": ["updated commercial operation date"],
        "actual_cod": ["actual in-service date"],
        "county": ["facility county"],
        "poi": ["substation"],
        "gen_type": ["generation type"],
        "net_mw": ["summer max capacity"],
        "ia_status": ["interconnection agreement status"],
        "notes": ["notes"],
    },
}
STATUS_MAP = {"ACTIVE": "ACTIVE", "IN SERVICE": "COMPLETED", "WITHDRAWN": "WITHDRAWN"}


def _find_header(path: Path, sheet=0) -> int:
    probe = pd.read_excel(path, sheet_name=sheet, header=None, nrows=8, dtype=str)
    for i, row in probe.iterrows():
        cells = row.astype(str).str.lower()
        if cells.str.contains("substation").any() and cells.str.contains("queue").any():
            return int(i)
    raise ValueError(f"{path.name}: no header row with 'Substation' and 'Queue' in the first 8 rows")


def inspect(path: Path) -> None:
    hdr = _find_header(path)
    df = pd.read_excel(path, header=hdr, dtype=str, nrows=5)
    print(f"{path.name}: header row {hdr + 1}")
    for c in df.columns:
        if not str(c).startswith("Unnamed"):
            print(f"  {str(c).strip()!r}: {df[c].dropna().astype(str).head(2).tolist()}")


def load_utility(util: str, path: Path | None = None) -> pd.DataFrame:
    path = Path(path) if path else DATA / FILES[util]
    if util not in MAPS:
        print(f"wdat: no column map for {util} — add one to MAPS (run `caiso-siting wdat inspect {path}`)")
        return pd.DataFrame()
    hdr = _find_header(path)
    raw = pd.read_excel(path, header=hdr, dtype=str)
    raw.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in raw.columns]
    low = {c.lower(): c for c in raw.columns}
    out = pd.DataFrame(index=raw.index)
    missing = []
    for canon, needles in MAPS[util].items():
        col = next((low[k] for k in low if any(n in k for n in needles)), None)
        if col is None:
            missing.append(canon)
            out[canon] = ""
        else:
            out[canon] = raw[col]
    if missing:
        print(f"wdat {util}: unmapped canonical columns {missing}")
    out = out[out["queue_position"].notna() & out["poi"].notna()].copy()
    out["utility"] = util
    out["queue_position"] = out.queue_position.astype(str).str.strip()
    out["status_raw"] = out.status.fillna("").str.strip()
    out["sheet_status"] = out.status_raw.str.upper().map(STATUS_MAP).fillna("")
    out["process"] = out.process.fillna("").str.strip()
    out["net_mw"] = pd.to_numeric(out.net_mw, errors="coerce")
    out["poi_mw"] = out.net_mw
    for c in ("request_received", "proposed_cod", "current_cod", "actual_cod"):
        out[c] = pd.to_datetime(out[c], errors="coerce", format="mixed")
    out["county"] = clean_county(out.county)
    out["poi"] = out.poi.fillna("").str.strip().str.upper()
    out = out[~out.poi.isin(["", "WITHDRAWN", "N/A", "TBD"])]
    gt = out.gen_type.fillna("").str.upper()
    out["has_storage"] = gt.str.contains("STORAGE|BATTERY")
    out["has_solar"] = gt.str.contains("SOLAR|PV")
    out["is_standalone_storage"] = out.has_storage & ~out.has_solar
    # the file carries one MW figure per request; attribute it to storage when the request is storage-only,
    # half when it is a solar+storage pair (the split is not published — say so if you quote it)
    out["storage_mw"] = out.net_mw.where(out.is_standalone_storage, out.net_mw / 2).where(out.has_storage, 0.0)
    out["poi_base"] = poi_base(out.poi)
    out["node_key"] = out.poi.map(norm_poi)
    out["queue_year"] = out.request_received.dt.year
    out["cluster"] = "WDAT-" + util
    return add_provenance(out, path.name)


def load_all() -> pd.DataFrame:
    frames = [load_utility(u) for u, f in FILES.items() if (DATA / f).exists()]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def per_node(w: pd.DataFrame) -> pd.DataFrame:
    if w.empty:
        return pd.DataFrame(columns=["wdat_active_projects", "wdat_active_mw", "wdat_active_storage_mw",
                                     "wdat_inservice_mw", "wdat_withdrawn_mw"])
    act = w[w.sheet_status == "ACTIVE"].groupby("node_key").agg(
        wdat_active_projects=("queue_position", "count"), wdat_active_mw=("net_mw", "sum"),
        wdat_active_storage_mw=("storage_mw", "sum"))
    ins = w[w.sheet_status == "COMPLETED"].groupby("node_key").net_mw.sum().rename("wdat_inservice_mw")
    wd = w[w.sheet_status == "WITHDRAWN"].groupby("node_key").net_mw.sum().rename("wdat_withdrawn_mw")
    return act.join(ins, how="outer").join(wd, how="outer").fillna(0).round(1)


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "inspect":
        if len(argv) < 2:
            sys.exit("usage: caiso-siting wdat inspect FILE.xlsx")
        inspect(Path(argv[1]))
        return
    OUT.mkdir(exist_ok=True)
    w = load_all()
    if w.empty:
        sys.exit(f"no WDAT files in {DATA} (expected any of {list(FILES.values())})")
    w.to_csv(OUT / "wdat_projects.csv", index=False)
    for u, s in w.groupby("utility"):
        print(f"{u}: {len(s)} requests | active {(s.sheet_status == 'ACTIVE').sum()} / "
              f"{s[s.sheet_status == 'ACTIVE'].net_mw.sum():,.0f} MW (storage-attributed {s[s.sheet_status == 'ACTIVE'].storage_mw.sum():,.0f} MW) | "
              f"in service {s[s.sheet_status == 'COMPLETED'].net_mw.sum():,.0f} MW | withdrawn {s[s.sheet_status == 'WITHDRAWN'].net_mw.sum():,.0f} MW")
        print(s[s.sheet_status == "ACTIVE"].groupby("process").net_mw.agg(["count", "sum"]).round(0).to_string())
    pn = per_node(w).sort_values("wdat_active_mw", ascending=False)
    print(f"\n{len(pn)} WDAT nodes; top 12 by active MW:")
    print(pn.head(12).to_string())
    print(f"wrote {OUT / 'wdat_projects.csv'}")


if __name__ == "__main__":
    main()
