"""
Transmission Plan Deliverability (TPD) allocation results — the column that turns
"Full Capacity requested" into "Full Capacity allocated".

Sources (CAISO, public xlsx):
  data/tpd_2024.xlsx  2024 allocation cycle results  (PTO, Q#/WDAT#, group, FCDSA/PCDSA, partial %)
  data/tpd_2025.xlsx  2025 allocation cycle results  (PTO, Q#/WDAT#, group, MW requested, allocation %)
  https://www.caiso.com/documents/2024-transmission-plan-deliverability-allocation-cycle-results.xlsx
  https://www.caiso.com/documents/2025-transmission-plan-deliverability-allocation-cycle-results.xlsx

Joined through the public report on queue position across ALL THREE of its sheets, so a node's TPD
history includes requests whose project has since withdrawn (5,505 MW requested / 450 MW allocated in
the 2025 cycle). That is deliberate — the allocation happened at that node — but it is not live
deliverability, and anything published from these columns must say so.

Join key: CAISO queue position ("Q#"). Rows keyed by WDAT numbers, "-WD", "CONV" or PTO codes are
distribution-level or conversion requests outside the public generator queue; they are kept in
outputs/tpd_allocations.csv but do not join to nodes.

Per-node columns added to nodes.csv:
  tpd25_projects        projects at the node that sought TPD in the 2025 cycle
  tpd25_req_mw          MW they requested
  tpd25_alloc_mw        MW allocated (requested × allocation %)
  tpd25_denied_mw       MW requested by rows that received exactly 0 % (an outright refusal)
  tpd25_unalloc_mw      requested - allocated: refused MW PLUS the remainder left by partial
                        allocations. Always >= tpd25_denied_mw; quote this one for "did not get".
  tpd25_unknown_mw      MW requested by rows with no allocation percentage in the file (0 today)
  tpd24_fcdsa_projects  projects allocated Full Capacity in the 2024 cycle
  tpd24_pcdsa_projects  projects allocated Partial Capacity in the 2024 cycle
  tpd25_req_{A,B,C,D}_mw / tpd25_denied_{A,B,C,D}_mw
                        the same request / refused MW split by CAISO allocation group (GROUPS below)
  tpd25_denied_ppa_mw   refused MW in groups A + B — projects that had (or were shortlisted for) a PPA.
                        A 0 % in group D is the expected outcome for a project without a PPA; a 0 % in
                        group A is a refusal of a contracted project and is the number to quote.
The 2024 file carries no MW, so 2024 is counts only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from .config import DATA, OUT, add_provenance

FILES = {2024: "tpd_2024.xlsx", 2025: "tpd_2025.xlsx"}

# CAISO allocation groups, ranked in allocation order. Wording from the 2025 Transmission Plan
# Deliverability Allocation Report (CAISO, 2026-04-13); tariff Appendix DD section 8.9.2.
GROUPS = {
    "A": "executed power purchase agreement requiring FCDS, or an LSE serving its own load",
    "B": "shortlisted for, or actively negotiating, a power purchase agreement",
    "C": "already in commercial operation for the capacity seeking TP deliverability",
    "D": "no PPA; electing the Section 8.9.2.3 (financial-security) path",
}
GROUP_ORDER = list(GROUPS)


def _find_header(path: Path) -> int:
    """The 2025 file has a title row above the header; the 2024 file does not."""
    probe = pd.read_excel(path, header=None, nrows=5, dtype=str)
    for i, row in probe.iterrows():
        cells = row.astype(str).str.upper()
        if cells.str.contains("PTO").any() and cells.str.contains("Q#|WDAT").any():
            return int(i)
    return 0


def load_year(year: int, path: Path | None = None) -> pd.DataFrame:
    path = Path(path) if path else DATA / FILES[year]
    df = pd.read_excel(path, header=_find_header(path), dtype=str)
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    cols = {c.lower(): c for c in df.columns}
    pick = lambda *keys: next((cols[k] for k in cols if any(x in k for x in keys)), None)
    c_pto, c_q, c_grp = pick("pto"), pick("q#", "wdat"), pick("group")
    out = pd.DataFrame({
        "tpd_year": year,
        "pto": df[c_pto].fillna("").str.strip().str.upper().replace({"PG&E": "PGAE", "SDG&E": "SDGE"}),
        "queue_id": df[c_q].fillna("").astype(str).str.strip(),
        "allocation_group": df[c_grp].fillna("").str.strip().str.upper(),
    })
    if year == 2024:
        c_status, c_pct = pick("status"), pick("percent")
        out["status"] = df[c_status].fillna("").str.strip().str.upper()
        pct = pd.to_numeric(df[c_pct], errors="coerce")
        out["allocation_pct"] = pct.where(out.status == "PCDSA", 1.0).where(out.status != "", float("nan"))
        out["mw_requested"] = float("nan")
    else:
        c_mw, c_pct = pick("mw requested"), pick("allocation percent", "percent")
        out["mw_requested"] = pd.to_numeric(df[c_mw], errors="coerce")
        out["allocation_pct"] = pd.to_numeric(df[c_pct], errors="coerce")
        out["status"] = pd.cut(out.allocation_pct.fillna(-1), [-2, -0.5, 0, 0.999, 1.0],
                               labels=["", "NONE", "PCDSA", "FCDSA"]).astype(str).replace("nan", "")
    req = pd.to_numeric(out.mw_requested, errors="coerce")
    pct = pd.to_numeric(out.allocation_pct, errors="coerce")
    out["mw_allocated"] = (req * pct).round(1)
    out["in_generator_queue"] = out.queue_id.str.fullmatch(r"\d+")
    out = out[out.queue_id != ""]
    return add_provenance(out, path.name)


def load_all() -> pd.DataFrame:
    frames = [load_year(y) for y, f in FILES.items() if (DATA / f).exists()]
    if not frames:
        return pd.DataFrame(columns=["tpd_year", "pto", "queue_id", "allocation_group", "status",
                                     "allocation_pct", "mw_requested", "mw_allocated", "in_generator_queue"])
    return pd.concat(frames, ignore_index=True)


def per_node(tpd: pd.DataFrame, projects: pd.DataFrame) -> pd.DataFrame:
    """projects: public-report rows with queue_position + node_key. Returns one row per node_key."""
    key = projects[["queue_position", "node_key"]].dropna().drop_duplicates("queue_position")
    key["queue_position"] = key.queue_position.astype(str).str.strip()
    t = tpd[tpd.in_generator_queue].merge(key, left_on="queue_id", right_on="queue_position", how="inner")
    t25 = t[t.tpd_year == 2025]
    t24 = t[t.tpd_year == 2024]
    g25 = t25.groupby("node_key").agg(
        tpd25_projects=("queue_id", "nunique"),
        tpd25_req_mw=("mw_requested", "sum"),
        tpd25_alloc_mw=("mw_allocated", "sum"),
        # exactly 0 % — a refusal. NaN is missing data, not a refusal, and is counted separately.
        tpd25_denied_mw=("mw_requested", lambda s: s[t25.loc[s.index, "allocation_pct"] == 0].sum()),
        tpd25_unknown_mw=("mw_requested", lambda s: s[t25.loc[s.index, "allocation_pct"].isna()].sum()),
    )
    # requested - allocated: the part that was refused outright PLUS the part a partial percentage
    # left behind. Publishing "denied" alone understates what a developer did not get.
    g25["tpd25_unalloc_mw"] = (g25.tpd25_req_mw - g25.tpd25_alloc_mw).round(1)
    # by allocation group: a refusal means something different for a contracted project (A) than for
    # one with no PPA (D). Groups outside A-D (none in the 2025 file) fall into the totals only.
    grp = t25.allocation_group.str.strip().str.upper().str.replace("GROUP ", "", regex=False)
    for g in GROUP_ORDER:
        sub = t25[grp == g]
        g25[f"tpd25_req_{g}_mw"] = sub.groupby("node_key").mw_requested.sum()
    for g in GROUP_ORDER:
        sub = t25[grp == g]
        g25[f"tpd25_denied_{g}_mw"] = sub[sub.allocation_pct == 0].groupby("node_key").mw_requested.sum()
    g25 = g25.fillna(0)
    g25["tpd25_denied_ppa_mw"] = g25.tpd25_denied_A_mw + g25.tpd25_denied_B_mw
    g24 = t24.groupby("node_key").agg(
        tpd24_fcdsa_projects=("status", lambda s: (s == "FCDSA").sum()),
        tpd24_pcdsa_projects=("status", lambda s: (s == "PCDSA").sum()),
    )
    return g25.join(g24, how="outer").fillna(0).round(1)


def node_rows(tpd: pd.DataFrame, projects: pd.DataFrame) -> pd.DataFrame:
    """Every generator-queue TPD request joined to its node and project name — one row per request,
    for the per-node pages (outputs/tpd_node_rows.csv)."""
    cols = ["node_key", "tpd_year", "queue_id", "project_name", "allocation_group", "status",
            "mw_requested", "allocation_pct", "mw_allocated"]
    if tpd.empty:
        return pd.DataFrame(columns=cols)
    key = projects.copy()
    if "project_name" not in key:
        key["project_name"] = ""
    key = key[["queue_position", "node_key", "project_name"]].dropna(subset=["queue_position", "node_key"]) \
        .drop_duplicates("queue_position")
    key["queue_position"] = key.queue_position.astype(str).str.strip()
    t = tpd[tpd.in_generator_queue].merge(key, left_on="queue_id", right_on="queue_position", how="inner")
    t["allocation_group"] = t.allocation_group.str.strip().str.upper().str.replace("GROUP ", "", regex=False)
    return t[cols].sort_values(["node_key", "tpd_year", "allocation_group", "queue_id"]).reset_index(drop=True)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    tpd = load_all()
    if tpd.empty:
        sys.exit(f"no TPD files in {DATA} (expected {list(FILES.values())})")
    tpd.to_csv(OUT / "tpd_allocations.csv", index=False)
    for y in sorted(tpd.tpd_year.unique()):
        s = tpd[tpd.tpd_year == y]
        gq = s[s.in_generator_queue]
        line = f"{y}: {len(s)} rows ({len(gq)} in generator queue)"
        if s.mw_requested.notna().any():
            line += (f"; requested {s.mw_requested.sum():,.0f} MW, allocated {s.mw_allocated.sum():,.0f} MW, "
                     f"{(s.allocation_pct == 0).sum()} rows at 0 %")
            gs = s.assign(_grp=s.allocation_group.str.replace("GROUP ", "", regex=False),
                          _den=s.mw_requested.where(s.allocation_pct == 0, 0.0))
            g = gs.groupby("_grp").agg(req=("mw_requested", "sum"), alloc=("mw_allocated", "sum"),
                                       denied=("_den", "sum")).round(0)
            line += "\n  by group: " + "; ".join(
                f"{k} {r.req:,.0f} req / {r.alloc:,.0f} alloc / {r.denied:,.0f} denied" for k, r in g.iterrows())
        else:
            line += f"; {(s.status == 'FCDSA').sum()} FCDSA, {(s.status == 'PCDSA').sum()} PCDSA"
        print(line)
        print(s.groupby("pto").agg(rows=("queue_id", "size"), req_mw=("mw_requested", "sum"),
                                   alloc_mw=("mw_allocated", "sum")).round(0).to_string())
    print(f"wrote {OUT / 'tpd_allocations.csv'}")


if __name__ == "__main__":
    main()
