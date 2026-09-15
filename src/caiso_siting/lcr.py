"""
Local Capacity Requirement (LCR) area per node — the Resource Adequacy geography.

For a battery in CAISO, location value is Resource Adequacy first and energy arbitrage second, and RA
value depends on whether the point of interconnection sits inside a Local Capacity Area (LA Basin,
Big Creek/Ventura, San Diego-Imperial Valley, Greater Bay Area, Greater Fresno, Kern, Sierra, Stockton,
North Coast/North Bay, Humboldt) and which sub-area / load pocket within it. CAISO publishes the area
definitions every year in the Local Capacity Technical Study (LCT report), as the list of substations
that DELINEATE each area: "X is out, Y is in". Only those boundary stations are named; interior stations
are not, so a blank here means "not encoded", never "outside every area".

  data/lcr_areas.csv   substation -> area / sub-area / relation (in|out), hand-encoded from the LCT report
                       with the report name and date in `source`. `utility` is optional and disambiguates
                       same-name stations (Eagle Rock: PG&E vs SCE). A station whose low-voltage bus is in
                       and high-voltage yard is out (Gates 70 vs 230 kV) is encoded OUT with a note, because
                       queue POIs sit on the high side.

Per-node columns added to nodes.csv:
  lcr_area       area the substation is INSIDE, e.g. "Greater Fresno"; "" when out or not encoded
  lcr_sub_area   sub-area when the report delineates it; "" otherwise
  lcr_status     "in <area>" | "outside <area>" | "" — the display form
  lcr_note       the report's qualification (voltage split, also-out-of, ...)
  lcr_source     the report the row came from
"""
from __future__ import annotations

import pandas as pd

from .common import norm_poi
from .config import DATA

LCR_COLS = ["lcr_area", "lcr_sub_area", "lcr_status", "lcr_note", "lcr_source"]
REQUIRED = ["substation", "lcr_area", "lcr_sub_area", "relation", "source", "source_date"]


def load(path=None) -> pd.DataFrame:
    """data/lcr_areas.csv -> one row per (node_key, utility). When a substation carries both an `in` and an
    `out` row for different areas, `in` wins (it is inside one area and on the boundary of another)."""
    path = path or DATA / "lcr_areas.csv"
    cols = ["node_key", "utility", *LCR_COLS]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path, dtype=str, comment="#").fillna("")
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    if "utility" not in df:
        df["utility"] = ""
    if "note" not in df:
        df["note"] = ""
    df = df[df.substation.str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["relation"] = df.relation.str.strip().str.lower()
    bad = sorted(set(df.relation) - {"in", "out"})
    if bad:
        raise ValueError(f"{path.name}: relation must be in|out, got {bad}")
    df["node_key"] = df.substation.map(norm_poi)
    df["utility"] = df.utility.str.strip().str.upper()
    df["_rank"] = (df.relation == "in").astype(int)
    df = df.sort_values(["_rank", "source_date"]).drop_duplicates(["node_key", "utility"], keep="last")
    is_in = df.relation == "in"
    out = pd.DataFrame({
        "node_key": df.node_key, "utility": df.utility,
        "lcr_area": df.lcr_area.str.strip().where(is_in, ""),
        "lcr_sub_area": df.lcr_sub_area.str.strip().where(is_in, ""),
        "lcr_status": ("in " + df.lcr_area.str.strip()).where(is_in, "outside " + df.lcr_area.str.strip()),
        "lcr_note": df.note.str.strip(),
        "lcr_source": df.source.str.strip() + " [" + df.source_date.str.strip() + "]",
    })
    return out.reset_index(drop=True)


def join(nodes: pd.DataFrame, path=None) -> pd.DataFrame:
    """Add the LCR columns to a nodes frame keyed on node_key (+ utility when the row names one)."""
    lcr = load(path)
    for c in LCR_COLS:
        nodes[c] = ""
    if lcr.empty:
        print("lcr: data/lcr_areas.csv has no rows — LCR columns are empty")
        return nodes
    util = nodes["utility"].fillna("").str.upper() if "utility" in nodes else pd.Series("", index=nodes.index)
    unmatched = []
    for _, r in lcr.iterrows():
        mask = nodes.node_key == r.node_key
        if r.utility:
            mask &= util == r.utility
        if not mask.any():
            # only worth a line when the station IS a queue node under another utility (a same-name collision)
            if r.utility and (nodes.node_key == r.node_key).any():
                unmatched.append(f"{r.node_key} ({r.utility} row; node is "
                                 f"{util[nodes.node_key == r.node_key].iloc[0] or 'blank'})")
            continue
        for c in LCR_COLS:
            nodes.loc[mask, c] = r[c]
    if unmatched:
        print(f"lcr: {len(unmatched)} encoded rows name a station whose queue node carries another utility "
              f"(same-name collision, left unlabelled): {'; '.join(unmatched)}")
    inside = nodes.lcr_area != ""
    outside = nodes.lcr_status.str.startswith("outside")
    print(f"lcr: {inside.sum()} nodes inside an encoded Local Capacity Area "
          f"({nodes.loc[inside, 'lcr_area'].value_counts().to_dict()}); {outside.sum()} named as outside one")
    return nodes
