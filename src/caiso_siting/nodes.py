#!/usr/bin/env python3
"""
Node table: unify the Public Queue Report + Cluster 15 report per Point of
Interconnection, geocode POIs, join official POI-availability statements, and
emit a Leaflet map + node_watch.md.

Inputs (all free):
  data/publicqueuereport.xlsx   CAISO public queue (Cluster 14 and earlier)
  data/cluster15.xlsx           CAISO Cluster 15 report
  data/osm_substations.csv      Overpass export (see README)
  data/poi_overrides.csv        hand-verified coordinates (win over OSM)
  data/poi_availability.csv     official per-POI availability statements (CAISO/PTO notices)
  data/lcr_areas.csv            Local Capacity Area / sub-area per substation (CAISO LCT report), see lcr.py
  data/eia860.zip               EIA-860 bulk zip: operating plants, owners, storage MWh, LMP nodes near each node, see eia860.py

Outputs:
  outputs/nodes.csv, poi_geocode.csv, nodes_map.html, node_watch.md

Metric definitions (read before quoting any of them):
  legacy_active_mw        active MW in the public report (C14 and earlier)
  c15_active_mw           active MW in the Cluster 15 report
  pipeline_mw             the two above
  operating_mw            completed MW in the public report
  wd_alltime_mw           every withdrawn MW since 2006 (includes dead wind/solar-era projects)
  wd_recent_mw            withdrawn in RECENT_FROM_YEAR..this year, both reports (a calendar-year window;
                          the current year is partial)
  wd_recent_storage_mw    storage MW of those rows — each project's storage components capped at its
                          net-to-grid figure. Equal to or below wd_recent_mw except for the handful of
                          filings that report net-to-grid as 0 (there the component MW is kept, so the
                          battery is not erased); 3 nodes today.
  wd_post_phase2_mw       withdrew AFTER Phase II / Facilities Study results (public report only)
  p2_reached_projects/mw  projects that received Phase II / Facilities Study results here (any sheet, public report)
  p2_withdrawn_projects/mw of those, the ones that then withdrew (== wd_post_phase2_mw)
  p2_attrition            p2_withdrawn_mw / p2_reached_mw — share of studied MW that left with results in hand
  committed_projects/mw   ACTIVE projects holding an executed interconnection agreement
  churn_n, c15_n, p2_n    project counts behind storage_churn, c15_survival, p2_attrition (small n = read with care)
  storage_churn           wd_recent_storage_mw / (active + operating storage MW)   <- the one to quote
  churn_alltime           wd_alltime_mw / (pipeline + operating MW)                 <- historical color only
  c15_survival            c15_active / (c15_active + c15_withdrawn)
  tpd25_req_mw            MW at the node that sought TPD in CAISO's 2025 allocation cycle
  tpd25_alloc_mw          MW allocated in that cycle (requested × allocation %)
  tpd25_denied_mw         MW requested by rows that received exactly 0 %
  tpd25_unalloc_mw        requested - allocated (refused + the remainder of partial allocations)
  tpd25_req_{A..D}_mw / tpd25_denied_{A..D}_mw   the same, split by CAISO allocation group (tpd.GROUPS)
  tpd25_denied_ppa_mw     refused MW in groups A+B (projects that had, or were shortlisted for, a PPA)
  tpd24_fcdsa_projects    projects at the node allocated Full Capacity in the 2024 cycle
  wdat_active_mw          MW of active WDAT (distribution-level) requests at the same substation (PG&E file today)
  wdat_inservice_mw       WDAT MW already in service at that substation
  lmp_tb4_12mo_mean       TB4 spread of day-ahead LMP at the confirmed PNode (mean of daily top-4 minus bottom-4 hours,
                          $/MWh, over the months fetched); a first-pass storage revenue screen, not a revenue forecast
  lmp_tb4_12mo_p90        the 90th percentile of the same daily TB4 spread
  lmp_months              months of OASIS data behind the two numbers (0 = no confirmed PNode / nothing fetched)
None of these say WHY anything withdrew. The files carry no reason beyond "IC Request".
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from . import cluster15, eia860, lcr, tpd, wdat
from . import queue_report as caiso_queue
from .common import haversine_km, in_state, norm_poi, poi_endpoints
from .config import DATA, OUT, RECENT_YEARS, add_provenance

RECENT_FROM_YEAR = pd.Timestamp.today().year - RECENT_YEARS + 1  # inclusive first year of the window

THIS_YEAR = pd.Timestamp.today().year
AMBIGUOUS_KM = 50   # OSM features sharing a name further apart than this make the position untrustworthy
APPROX_METHODS = ["line-one-end", "line-midpoint", "fuzzy", "override-approx", "county-centroid", "ambiguous",
                  "state-mismatch", "none", "disputed"]


# ------------------------------------------------------------------ geocoding

def load_osm(path: Path) -> pd.DataFrame:
    osm = pd.read_csv(path, dtype=str, quotechar='"', on_bad_lines="skip")
    osm.columns = [c.strip().lstrip("@") for c in osm.columns]
    osm = osm.rename(columns={"id": "osm_id", "type": "osm_type"})
    osm["lat"] = pd.to_numeric(osm["lat"], errors="coerce")
    osm["lon"] = pd.to_numeric(osm["lon"], errors="coerce")
    osm = osm.dropna(subset=["lat", "lon"])
    osm = osm[osm["name"].notna() & (osm["name"].str.strip() != "")].copy()
    osm["key"] = osm["name"].map(norm_poi)
    osm["kv"] = osm["voltage"].fillna("").str.extract(r"(\d{4,6})", expand=False).astype(float) / 1000
    return osm[osm["key"] != ""].reset_index(drop=True)


class Geocoder:
    def __init__(self, osm: pd.DataFrame, overrides_path: Path = DATA / "poi_overrides.csv"):
        self.osm = osm
        self.by_key: dict[str, list[int]] = {}
        for i, k in enumerate(osm["key"]):
            self.by_key.setdefault(k, []).append(i)
        self.keys = list(self.by_key)
        self.overrides: dict[str, dict] = {}
        if overrides_path.exists():
            ov = pd.read_csv(overrides_path, dtype=str, comment="#").dropna(subset=["poi", "lat", "lon"])
            for _, r in ov.iterrows():
                self.overrides[norm_poi(r["poi"])] = dict(lat=float(r["lat"]), lon=float(r["lon"]),
                                                          note=str(r.get("note", "manual"))[:80],
                                                          approx=str(r.get("approx", "no")).strip().lower() == "yes")

    def _pick(self, idxs, state: str | None = None):
        """Choose among OSM features that share a name. A candidate inside the state the developer
        filed wins over a higher-voltage one elsewhere (OSM has a 'Valley Substation' in Riverside CA
        and CAISO has a VALLEY SWITCH in Nye NV). The picked row carries `_ambiguous` when the
        surviving candidates are more than AMBIGUOUS_KM apart, so the caller can flag the position."""
        sub = self.osm.loc[list(idxs)]
        if state:
            keep = sub[[in_state(r.lat, r.lon, state) is not False for r in sub.itertuples()]]
            if len(keep):
                sub = keep
        ambiguous = False
        if len(sub) > 1:
            lat0, lon0 = sub.lat.iloc[0], sub.lon.iloc[0]
            ambiguous = any(haversine_km(lat0, lon0, r.lat, r.lon) > AMBIGUOUS_KM for r in sub.itertuples())
        row = sub.sort_values("kv", ascending=False, na_position="last").iloc[0].copy()
        row["_ambiguous"] = ambiguous
        return row

    def match(self, name: str, state: str | None = None):
        k = norm_poi(name)
        if not k:
            return None, 0.0
        if k in self.by_key:
            return self._pick(self.by_key[k], state), 1.0
        toks = set(k.split())
        cands = [kk for kk in self.keys if toks <= set(kk.split()) or set(kk.split()) <= toks]
        best, score = None, 0.0
        for kk in (cands or self.keys):
            s = SequenceMatcher(None, k, kk).ratio()
            if s > score:
                best, score = kk, s
        # fuzzy must share the first token: MOSS LANDING != CROWS LANDING, EAST COUNTY != EAST CITY
        if best is None or score < 0.85 or best.split()[0] != k.split()[0]:
            return None, score
        return self._pick(self.by_key[best], state), score

    def geocode_poi(self, poi: str, state: str | None = None) -> dict:
        r = self._geocode(poi, state)
        # A position outside the state the developer filed is provably wrong: demote it rather than
        # publish it. The county-centroid fallback then places the node (from same-state nodes only).
        if r["lat"] is not None and in_state(r["lat"], r["lon"], state) is False and r["method"] != "override":
            return dict(lat=None, lon=None, osm_name=f"rejected: {r['osm_name']} is not in {state}",
                        score=0.0, method="state-mismatch")
        return r

    def _geocode(self, poi: str, state: str | None = None) -> dict:
        k = norm_poi(poi)
        if k in self.overrides:
            o = self.overrides[k]
            return dict(lat=o["lat"], lon=o["lon"], osm_name=o["note"],
                        score=0.8 if o["approx"] else 1.0, method="override-approx" if o["approx"] else "override")
        whole, ws = self.match(poi, state)                # "VACA-DIXON" is one substation
        if whole is not None and ws == 1.0:
            amb = bool(whole.get("_ambiguous"))
            return dict(lat=whole.lat, lon=whole.lon, osm_name=whole["name"],
                        score=0.5 if amb else 1.0, method="ambiguous" if amb else "exact")
        ends = poi_endpoints(poi)
        # an override may exist for one endpoint (e.g. HARLAN in "MANNING-HARLAN")
        hits = []
        for e in ends:
            if e in self.overrides:
                o = self.overrides[e]
                hits.append((pd.Series(dict(lat=o["lat"], lon=o["lon"], name=o["note"])), 1.0))
            else:
                hits.append(self.match(e, state))
        good = [(r, s) for r, s in hits if r is not None]
        if not good:
            return dict(lat=None, lon=None, osm_name=None, score=max(s for _, s in hits), method="none")
        if len(ends) == 2 and len(good) == 2:
            (a, sa), (b, sb) = good
            return dict(lat=(a.lat + b.lat) / 2, lon=(a.lon + b.lon) / 2,
                        osm_name=f"{a['name']} | {b['name']}", score=min(sa, sb), method="line-midpoint")
        r, s = good[0]
        if len(ends) == 2:  # line POI, one end resolved: position is NOT the tap point
            return dict(lat=r.lat, lon=r.lon, osm_name=r["name"], score=round(s * 0.7, 2), method="line-one-end")
        return dict(lat=r.lat, lon=r.lon, osm_name=r["name"], score=s, method="exact" if s == 1.0 else "fuzzy")


# ------------------------------------------------------------------ node table

def load_projects() -> tuple[pd.DataFrame, pd.DataFrame]:
    pq = caiso_queue.load_all(DATA / "publicqueuereport.xlsx")
    c15 = cluster15.load(DATA / "cluster15.xlsx")
    # Dedupe guard: once CAISO folds Cluster 15 into the public report, the same queue
    # position will appear in both files. The public report wins (later status).
    dup = c15["queue_position"].isin(set(pq["queue_position"].dropna()))
    if dup.any():
        print(f"dedupe: dropping {dup.sum()} Cluster 15 rows already present in the public report")
        c15 = c15[~dup].copy()
    return pq, c15


def build_nodes(pq: pd.DataFrame, c15: pd.DataFrame) -> pd.DataFrame:
    key = "node_key"

    def agg(df, mask, prefix, extra=None):
        sub = df[mask]
        spec = {f"{prefix}_projects": ("project_name", "count"),
                f"{prefix}_mw": ("net_mw", "sum"),
                f"{prefix}_storage_mw": ("storage_mw", "sum")}
        return sub.groupby(key).agg(**spec)

    both = pd.concat([pq, c15], ignore_index=True, sort=False)
    both = both[both[key] != ""]
    recent = both["withdrawn_year"].fillna(0) >= RECENT_FROM_YEAR
    wd = both["sheet_status"] == "WITHDRAWN"
    p2 = pq.get("study_fas_phase2", pd.Series("", index=pq.index)).fillna("").str.upper() == "COMPLETE"
    if "ia_status" not in pq:
        pq = pq.assign(ia_status="")

    parts = [
        agg(pq, pq.sheet_status == "ACTIVE", "legacy_active"),
        agg(c15, c15.sheet_status == "ACTIVE", "c15_active"),
        agg(pq, pq.sheet_status == "COMPLETED", "operating"),
        agg(both, wd, "wd_alltime"),
        agg(both, wd & recent, "wd_recent"),
        agg(c15, c15.sheet_status == "WITHDRAWN", "c15_withdrawn"),
        pq[pq["withdrew_post_phase2"]].groupby(key).net_mw.sum().rename("wd_post_phase2_mw").to_frame(),
        c15[(c15.sheet_status == "ACTIVE") & c15.deliverability.str.startswith("FULL")]
            .groupby(key).net_mw.sum().rename("c15_fcds_req_mw").to_frame(),
        # Phase II attrition: of the projects that RECEIVED Phase II / Facilities Study results at this node
        # (public report, study column == COMPLETE, any sheet), how many and how much then withdrew. The closest
        # public proxy for "did people leave once they saw the upgrade costs" — still not a cause.
        agg(pq, p2, "p2_reached"),
        agg(pq, p2 & (pq.sheet_status == "WITHDRAWN"), "p2_withdrawn"),
        # Commitment: active projects that hold an executed interconnection agreement. Financial security is
        # posted against study costs that are not public, so this is the only public commitment signal.
        agg(pq, (pq.sheet_status == "ACTIVE") & (pq.ia_status.fillna("").str.upper() == "EXECUTED"), "committed"),
    ]
    nodes = parts[0]
    for p in parts[1:]:
        nodes = nodes.join(p, how="outer")
    nodes = nodes.fillna(0)

    if "state" not in both:
        both["state"] = ""
    labels = both.groupby(key).agg(
        poi_base=("poi_base", lambda s: s.mode().iloc[0]),
        county=("county", sole_mode),
        utility=("utility", sole_mode),
        state=("state", sole_mode))
    nodes = labels.join(nodes, how="right").fillna({"poi_base": "", "county": "", "utility": "", "state": ""}).reset_index()
    nodes = nodes[nodes[key] != ""]

    nodes["pipeline_mw"] = nodes.legacy_active_mw + nodes.c15_active_mw
    nodes["pipeline_storage_mw"] = nodes.legacy_active_storage_mw + nodes.c15_active_storage_mw
    nz = lambda s: s.replace(0, float("nan"))
    nodes["storage_churn"] = (nodes.wd_recent_storage_mw /
                              nz(nodes.pipeline_storage_mw + nodes.operating_storage_mw)).round(2)
    nodes["churn_alltime"] = (nodes.wd_alltime_mw / nz(nodes.pipeline_mw + nodes.operating_mw)).round(2)
    nodes["c15_survival"] = (nodes.c15_active_mw / nz(nodes.c15_active_mw + nodes.c15_withdrawn_mw)).round(2)
    nodes["p2_attrition"] = (nodes.p2_withdrawn_mw / nz(nodes.p2_reached_mw)).round(2)
    # project counts behind each ratio, so a 3.33 built on two rows can be shown for what it is
    nodes["churn_n"] = (nodes.wd_recent_projects + nodes.legacy_active_projects + nodes.c15_active_projects
                        + nodes.operating_projects).astype(int)
    nodes["c15_n"] = (nodes.c15_active_projects + nodes.c15_withdrawn_projects).astype(int)
    nodes["p2_n"] = nodes.p2_reached_projects.astype(int)
    return nodes.sort_values("pipeline_mw", ascending=False).reset_index(drop=True)


TPD_COLS = (["tpd25_projects", "tpd25_req_mw", "tpd25_alloc_mw", "tpd25_denied_mw", "tpd25_unknown_mw",
             "tpd25_unalloc_mw"]
            + [f"tpd25_req_{g}_mw" for g in tpd.GROUP_ORDER] + [f"tpd25_denied_{g}_mw" for g in tpd.GROUP_ORDER]
            + ["tpd25_denied_ppa_mw", "tpd24_fcdsa_projects", "tpd24_pcdsa_projects"])


def join_tpd(nodes: pd.DataFrame, pq: pd.DataFrame) -> pd.DataFrame:
    """Allocated deliverability per node from CAISO's TPD allocation cycle results (data/tpd_*.xlsx).
    Joined through the public report on queue position — all sheets, because a project allocated in
    2024 may have withdrawn since and its node should still show the history."""
    t = tpd.load_all()
    if t.empty:
        for c in TPD_COLS:
            nodes[c] = 0.0
        print("tpd: no data/tpd_*.xlsx files — TPD columns are zero")
        return nodes
    pn = tpd.per_node(t, pq)
    nodes = nodes.merge(pn, left_on="node_key", right_index=True, how="left")
    for c in TPD_COLS:
        nodes[c] = nodes[c].fillna(0.0)
    hit = nodes.tpd25_projects > 0
    print(f"tpd: {hit.sum()} nodes with 2025 TPD requests; requested {nodes.tpd25_req_mw.sum():,.0f} MW, "
          f"allocated {nodes.tpd25_alloc_mw.sum():,.0f} MW, denied {nodes.tpd25_denied_mw.sum():,.0f} MW "
          f"(of which {nodes.tpd25_denied_ppa_mw.sum():,.0f} MW in groups A+B, i.e. with a PPA or shortlist)")
    return nodes


WDAT_COLS = ["wdat_active_projects", "wdat_active_mw", "wdat_active_storage_mw", "wdat_inservice_mw", "wdat_withdrawn_mw"]


def join_wdat(nodes: pd.DataFrame) -> pd.DataFrame:
    """Distribution-level (WDAT) queue activity at the same substation, from data/wdat_*.xlsx.
    Only substations that already exist as CAISO nodes are joined here; WDAT-only substations live in
    outputs/wdat_projects.csv (they are a different market: no CAISO deliverability unless studied)."""
    w = wdat.load_all()
    if w.empty:
        for c in WDAT_COLS:
            nodes[c] = 0.0
        print("wdat: no data/wdat_*.xlsx files — WDAT columns are zero")
        return nodes
    pn = wdat.per_node(w)
    nodes = nodes.merge(pn, left_on="node_key", right_index=True, how="left")
    for c in WDAT_COLS:
        nodes[c] = nodes[c].fillna(0.0)
    hit = nodes.wdat_active_projects > 0
    print(f"wdat: {hit.sum()} CAISO nodes also carry active WDAT requests ({nodes.wdat_active_mw.sum():,.0f} MW); "
          f"{len(pn) - hit.sum()} WDAT-only substations not in the CAISO node table")
    return nodes


LMP_COLS = ["lmp_tb4_12mo_mean", "lmp_tb4_12mo_p90", "lmp_months"]


def join_lmp(nodes: pd.DataFrame) -> pd.DataFrame:
    """Day-ahead LMP TB4 spread per node from outputs/lmp_tb4_summary.csv (`caiso-siting oasis fetch`, run from a
    terminal). Only nodes with a hand-confirmed PNode in data/poi_pnodes.csv carry values; everything else is NaN
    with lmp_months = 0. A first-pass storage revenue screen, not a revenue forecast."""
    path = OUT / "lmp_tb4_summary.csv"
    if not path.exists():
        nodes["lmp_tb4_12mo_mean"] = float("nan")
        nodes["lmp_tb4_12mo_p90"] = float("nan")
        nodes["lmp_months"] = 0
        print("lmp: no outputs/lmp_tb4_summary.csv — LMP columns are empty (run `caiso-siting oasis fetch`)")
        return nodes
    s = pd.read_csv(path, dtype={"node_key": str}).drop_duplicates("node_key").set_index("node_key")
    nodes["lmp_tb4_12mo_mean"] = nodes["node_key"].map(pd.to_numeric(s["tb4_12mo_mean"], errors="coerce"))
    nodes["lmp_tb4_12mo_p90"] = nodes["node_key"].map(pd.to_numeric(s["tb4_12mo_p90"], errors="coerce"))
    nodes["lmp_months"] = nodes["node_key"].map(pd.to_numeric(s["months"], errors="coerce")).fillna(0).astype(int)
    hit = nodes.lmp_months > 0
    print(f"lmp: {hit.sum()} nodes with day-ahead TB4 from OASIS ({len(s) - hit.sum()} summary rows not in the node table)")
    return nodes


def join_availability(nodes: pd.DataFrame) -> pd.DataFrame:
    path = DATA / "poi_availability.csv"
    nodes["c16_poi_status"] = ""
    nodes["c16_poi_note"] = ""
    if not path.exists():
        return nodes
    av = pd.read_csv(path, dtype=str, comment="#").fillna("")
    av["node_key"] = av["poi"].map(norm_poi)
    av = av.sort_values("date").groupby("node_key").last()   # latest statement wins
    m = nodes["node_key"].map(av["status"])
    nodes["c16_poi_status"] = m.fillna("")
    nodes["c16_poi_note"] = nodes["node_key"].map(av["note"] + " [" + av["date"] + "]").fillna("")
    hit = nodes.c16_poi_status != ""
    print(f"availability: {hit.sum()} nodes carry an official C16 POI statement: "
          f"{nodes.loc[hit, ['poi_base', 'c16_poi_status']].values.tolist()}")
    return nodes


def geocode_nodes(nodes: pd.DataFrame) -> pd.DataFrame:
    osm_path = DATA / "osm_substations.csv"
    gc = Geocoder(load_osm(osm_path) if osm_path.exists() else pd.DataFrame(columns=["key", "name", "lat", "lon", "voltage"]),
                  DATA / "poi_overrides.csv")
    rows = []
    for nk, poi, st in nodes[["node_key", "poi_base", "state"]].drop_duplicates("node_key").itertuples(index=False):
        r = gc.geocode_poi(poi, st)
        rows.append(dict(node_key=nk, poi_base=poi, lat=r["lat"], lon=r["lon"], osm_name=r["osm_name"],
                         geo_score=round(r["score"], 2), geo_method=r["method"]))
    geo = pd.DataFrame(rows)
    geo.to_csv(OUT / "poi_geocode.csv", index=False)
    nodes = nodes.merge(geo.drop(columns="poi_base"), on="node_key", how="left")
    nodes = apply_line_cache(nodes)
    nodes = county_centroid_fallback(nodes)
    # Last, so a quarantined node is not quietly rescued by the centroid fallback: a position we
    # have proven wrong should read as "disputed", not as "we never knew".
    nodes = quarantine_positions(nodes)
    located = nodes.lat.notna() & (nodes.geo_method != "county-centroid")
    print(f"geocode: {located.sum()}/{len(nodes)} nodes located ({located.mean():.0%}); "
          f"{nodes.loc[located, 'pipeline_mw'].sum() / nodes.pipeline_mw.sum():.0%} of pipeline MW; "
          f"methods {nodes.geo_method.value_counts().to_dict()}")
    return nodes


def apply_line_cache(nodes: pd.DataFrame) -> pd.DataFrame:
    """data/poi_lines.csv (from `caiso-siting layers lines`) places line POIs on CEC line geometry.
    It only replaces positions that are one-end or missing; hand overrides and exact matches stand."""
    path = DATA / "poi_lines.csv"
    if not path.exists():
        return nodes
    cache = pd.read_csv(path).drop_duplicates("node_key").set_index("node_key")
    hit = nodes.node_key.isin(cache.index) & nodes.geo_method.isin(["line-one-end", "none"])
    nodes.loc[hit, "lat"] = nodes.loc[hit, "node_key"].map(cache.lat).values
    nodes.loc[hit, "lon"] = nodes.loc[hit, "node_key"].map(cache.lon).values
    nodes.loc[hit, "geo_method"] = "cec-line"
    nodes.loc[hit, "geo_score"] = 0.9
    kv = cache.kv.map(lambda v: "" if pd.isna(v) or str(v).strip().lower() in ("", "nan", "none") else f" {v} kV")
    nodes.loc[hit, "osm_name"] = ("CEC line: " + cache.tline_name.astype(str) + kv)\
        .reindex(nodes.loc[hit, "node_key"]).values
    print(f"cec-line cache: {hit.sum()} line POIs placed on transmission-line geometry")
    return nodes


def sole_mode(s: pd.Series) -> str:
    """Modal label, but ONLY when the mode is unique.

    county/utility/state on a node are the *projects'* labels, not the POI's, so a node whose
    projects disagree is a node whose label is unknown. pandas breaks a tie alphabetically, which
    silently published PGAE on Los Angeles County substations (EAGLE ROCK, EL NIDO) and then made
    them match the wrong local-capacity row. A tie is ambiguity, and ambiguity is blank.
    """
    s = s.fillna("")
    s = s[s != ""]
    if s.empty:
        return ""
    m = s.mode()
    return "" if len(m) > 1 else str(m.iloc[0])


def quarantine_positions(nodes: pd.DataFrame) -> pd.DataFrame:
    """Drop positions that a review proved wrong.

    A confidently wrong coordinate is worse than no coordinate: it is drawn on the map, it is used
    to attribute EIA-860 plants by distance, and it carries a high geo_score while doing it. Nodes
    listed in data/geo_quarantine.csv lose their position and are marked `disputed`, which is not
    in REAL_POSITIONS, so nothing joins on them until a sourced override replaces the coordinate.
    """
    f = DATA / "geo_quarantine.csv"
    if not f.exists():
        return nodes
    q = pd.read_csv(f, comment="#")
    hit = nodes.node_key.isin(q.node_key)
    if hit.any():
        nodes.loc[hit, ["lat", "lon", "geo_score", "osm_name"]] = float("nan"), float("nan"), float("nan"), ""
        nodes.loc[hit, "geo_method"] = "disputed"
        print(f"geo: quarantined {int(hit.sum())} proven-wrong position(s): "
              f"{', '.join(sorted(nodes.loc[hit, 'node_key']))}")
    return nodes


def county_centroid_fallback(nodes: pd.DataFrame) -> pd.DataFrame:
    """Unlocated nodes get the median position of *located* nodes in the same county, flagged
    `county-centroid` (score 0.3) so aggregate maps stop silently omitting a fifth of the MW.
    Multi-county strings ("KERN/KINGS") use the first county. Never used for anything but display."""
    loc = nodes[nodes.lat.notna() & ~nodes.geo_method.isin(["county-centroid"])].copy()
    # only source positions that are inside the state they were filed under (an out-of-state
    # geocode would otherwise drag every unlocated node in that county across the border)
    if loc.empty:                       # nothing located (e.g. no OSM file): nothing to anchor to
        print("county-centroid fallback: no located nodes to anchor to — skipped")
        return nodes
    loc = loc[pd.Series([in_state(r.lat, r.lon, r.state) is not False for r in loc.itertuples()],
                        index=loc.index, dtype=bool)]
    loc["c1"] = loc.state.fillna("") + "|" + loc.county.str.split("/").str[0]
    cent = loc.groupby("c1").agg(lat=("lat", "median"), lon=("lon", "median"), n=("lat", "size"))
    cent = cent[cent.n >= 3]
    miss = nodes.lat.isna()
    c1 = nodes.state.fillna("") + "|" + nodes.county.fillna("").str.split("/").str[0]
    hit = miss & c1.isin(cent.index)
    nodes.loc[hit, "lat"] = c1[hit].map(cent.lat).values
    nodes.loc[hit, "lon"] = c1[hit].map(cent.lon).values
    nodes.loc[hit, "geo_method"] = "county-centroid"
    nodes.loc[hit, "geo_score"] = 0.3
    nodes.loc[hit, "osm_name"] = "median of located nodes in " + c1[hit].str.replace("|", " ", regex=False)
    print(f"county-centroid fallback: {hit.sum()} nodes placed at county centroids ({nodes.loc[hit, 'pipeline_mw'].sum():,.0f} MW)")
    return nodes


# ------------------------------------------------------------------ outputs

def write_map(nodes: pd.DataFrame) -> None:
    pts = nodes[nodes.lat.notna() & (nodes.pipeline_mw > 0)]
    f = lambda v: None if pd.isna(v) else float(v)
    feats = [dict(lat=r.lat, lon=r.lon, poi=r.poi_base, county=r.county, utility=r.utility,
                  legacy=round(r.legacy_active_mw), c15=round(r.c15_active_mw), op=round(r.operating_mw),
                  wdr=round(r.wd_recent_mw), wdrs=round(r.wd_recent_storage_mw), wda=round(r.wd_alltime_mw),
                  p2=round(r.wd_post_phase2_mw), sc=f(r.storage_churn), surv=f(r.c15_survival),
                  st=r.c16_poi_status, note=r.c16_poi_note, score=r.geo_score, method=r.geo_method, osm=r.osm_name)
             for _, r in pts.iterrows()]
    # '</' -> '<\/' so no source string can close the <script> block (valid JSON, identical in JS)
    pts_json = json.dumps(feats).replace("</", "<\\/")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>CAISO interconnection nodes</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>html,body,#m{{height:100%;margin:0;font-family:system-ui}} .lg{{background:#fff;padding:8px 10px;border-radius:6px;font-size:12px;line-height:1.55;max-width:260px}}</style>
</head><body><div id="m"></div><script>
const pts={pts_json};
const esc=v=>v==null?'':String(v).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const m=L.map('m').setView([36.3,-119.3],6);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'&copy; OpenStreetMap; data: CAISO public queue + Cluster 15 reports + CAISO POI notices'}}).addTo(m);
const col=c=> c==null?'#9a9a9a': c<0.25?'#2a9d8f': c<1?'#e9c46a':'#e63946';
for(const p of pts){{
  const mw=p.legacy+p.c15; const r=Math.max(4,Math.sqrt(mw)/2.2);
  const approx = ['line-one-end','fuzzy','override-approx','county-centroid','cec-line','ambiguous','state-mismatch'].includes(p.method);
  const centroid = p.method==='county-centroid';
  const ring = p.st==='UNAVAILABLE'?'#000': p.st==='AVAILABLE'?'#1d4ed8':'#222';
  L.circleMarker([p.lat,p.lon],{{radius:r,color:ring,weight:p.st?3:1,dashArray:approx?'3,3':null,fillColor:col(p.sc),fillOpacity:approx?.25:.75}})
   .bindPopup(`<b>${{esc(p.poi)}}</b><br>${{esc(p.county)}} / ${{esc(p.utility)}}`+
     (p.st?`<br><b>C16 POI: ${{esc(p.st)}}</b> — ${{esc(p.note)}}`:'')+
     `<br>Legacy active ${{p.legacy}} MW · C15 active ${{p.c15}} MW · Operating ${{p.op}} MW`+
     `<br>Withdrawn last {RECENT_YEARS}y: ${{p.wdr}} MW (storage ${{p.wdrs}}) · after Phase II: ${{p.p2}} MW · all-time ${{p.wda}} MW`+
     `<br>Storage churn: ${{p.sc??'n/a'}} · C15 survival: ${{p.surv??'n/a'}}`+
     `<br><small>geocode ${{esc(p.method)}} ${{esc(p.score)}} → ${{esc(p.osm)}}${{approx?' — APPROXIMATE, not the tap point':''}}</small>`).addTo(m);
}}
const lg=L.control({{position:'bottomleft'}}); lg.onAdd=()=>{{const d=L.DomUtil.create('div','lg');
d.innerHTML='<b>Size</b> = pipeline MW (legacy + C15)<br><b>Fill</b> = storage churn since {RECENT_FROM_YEAR} (withdrawn storage ÷ surviving storage)<br>'+
'<span style="color:#2a9d8f">●</span> &lt;0.25 <span style="color:#e9c46a">●</span> 0.25–1 <span style="color:#e63946">●</span> &gt;1 <span style="color:#9a9a9a">●</span> n/a<br>'+
'<b>Ring</b>: <span style="color:#1d4ed8">blue</span> = stated AVAILABLE for C16, black = UNAVAILABLE<br>'+
'Dashed/pale = approximate (line POI or fuzzy match); hollow = county centroid, position unknown';return d;}}; lg.addTo(m);
</script></body></html>"""
    (OUT / "nodes_map.html").write_text(html)


def tpd_from_withdrawn(pq: pd.DataFrame) -> tuple[float, float]:
    """How much of the 2025 TPD table belongs to projects the public report now lists as withdrawn."""
    try:
        t = tpd.load_all()
        if t.empty:
            return 0.0, 0.0
        key = pq[pq.sheet_status == "WITHDRAWN"][["queue_position"]].dropna()
        key["queue_position"] = key.queue_position.astype(str).str.strip()
        m = t[(t.tpd_year == 2025) & t.in_generator_queue].merge(key, left_on="queue_id", right_on="queue_position")
        return float(m.mw_requested.sum()), float(m.mw_allocated.sum())
    except Exception:  # noqa: BLE001
        return 0.0, 0.0


def write_node_watch(nodes: pd.DataFrame, pq: pd.DataFrame, c15: pd.DataFrame) -> None:
    a15 = c15[c15.sheet_status == "ACTIVE"]
    w15 = c15[c15.sheet_status == "WITHDRAWN"]
    pqa = pq[pq.sheet_status == "ACTIVE"]
    pqw = pq[pq.sheet_status == "WITHDRAWN"]

    def tbl(df, cols):
        d = df[cols].copy()
        for c in cols:
            if c.endswith("_mw"):
                d[c] = d[c].round(0).astype(int)
            elif c in ("storage_churn", "churn_alltime", "c15_survival"):
                d[c] = d[c].round(2)
        return d.to_markdown(index=False)

    top = nodes.head(12)
    hot = nodes[(nodes.pipeline_storage_mw + nodes.operating_storage_mw > 300) & (nodes.wd_recent_storage_mw > 300)] \
        .sort_values("storage_churn", ascending=False).head(10)
    post2 = nodes[nodes.wd_post_phase2_mw > 0].sort_values("wd_post_phase2_mw", ascending=False).head(10)
    clean = nodes[(nodes.c15_active_mw > 0) & (nodes.wd_recent_mw < 300)].sort_values("c15_active_mw", ascending=False).head(8)
    survivors = nodes[nodes.c15_withdrawn_mw + nodes.c15_active_mw > 500].sort_values("c15_survival").head(8)
    avail = nodes[nodes.c16_poi_status != ""].sort_values("c16_poi_status")
    tpd_tbl = nodes[nodes.tpd25_req_mw > 0].sort_values("tpd25_req_mw", ascending=False).head(15)
    lcr_in = nodes[(nodes.lcr_area != "") & ((nodes.pipeline_mw > 0) | (nodes.operating_mw > 0))] \
        .sort_values("pipeline_mw", ascending=False).head(15)
    lcr_out = nodes[nodes.lcr_status.str.startswith("outside") & (nodes.pipeline_mw >= 500)] \
        .sort_values("pipeline_mw", ascending=False)
    approx = nodes[(nodes.pipeline_mw > 500) & nodes.geo_method.isin(APPROX_METHODS)] \
        .sort_values("pipeline_mw", ascending=False)
    wd_recent_all = pd.concat([pqw, w15]).pipe(lambda d: d[d.withdrawn_year.fillna(0) >= RECENT_FROM_YEAR])
    wd_tpd_req, wd_tpd_alloc = tpd_from_withdrawn(pq)
    tpd_grp = "; ".join(
        f"group {g}: {nodes[f'tpd25_req_{g}_mw'].sum():,.0f} MW requested, {nodes[f'tpd25_denied_{g}_mw'].sum():,.0f} denied"
        for g in tpd.GROUP_ORDER if f"tpd25_req_{g}_mw" in nodes and nodes[f"tpd25_req_{g}_mw"].sum() > 0) or "no group data"

    whirl = nodes[nodes.node_key == "WHIRLWIND"].iloc[0] if (nodes.node_key == "WHIRLWIND").any() else None
    whirl_txt = ""
    if whirl is not None:
        whirl_txt = (f"Example of why the window matters — Whirlwind (Kern, SCE): all-time churn {whirl.churn_alltime:.2f} "
                     f"looks like a graveyard; storage churn since {RECENT_FROM_YEAR} is {whirl.storage_churn:.2f}, "
                     f"with {whirl.operating_mw:,.0f} MW operating and {whirl.pipeline_mw:,.0f} MW in pipeline. "
                     f"The old number describes 2008-era wind projects, not today's batteries.")

    run_date = str(pq["source_run_date"].dropna().iloc[0]) if "source_run_date" in pq and pq["source_run_date"].notna().any() else "unknown"
    md = f"""# CAISO Node Watch — draft {pd.Timestamp.today():%Y-%m-%d}

Sources: CAISO Public Queue Report (run date {run_date}), CAISO Cluster 15 report (posted 2026-07-16),
CAISO notice "PG&E information on POI availability for Cluster 16" (2026-01-15), OpenStreetMap substations (ODbL).
All MW are net-to-grid as filed. No figure below states a *cause*; the CAISO files carry none.

## The state of the queue in three numbers

- **Legacy pipeline (Cluster 14 and earlier):** {len(pqa)} active projects, {pqa.net_mw.sum():,.0f} MW,
  {pqa.has_storage.mean():.0%} with storage, {(pqa.ia_status == "EXECUTED").sum()} already under executed IAs.
- **Cluster 15 today:** {len(a15)} active projects, {a15.net_mw.sum():,.0f} MW ({a15.storage_mw.sum():,.0f} MW storage).
  {len(w15)} projects / {w15.net_mw.sum():,.0f} MW have withdrawn — {w15.net_mw.sum() / (a15.net_mw.sum() + w15.net_mw.sum()):.0%}
  of the {a15.net_mw.sum() + w15.net_mw.sum():,.0f} MW this file records as entering the cluster.
  (CAISO's July 2025 briefing put the studied set at 145 projects / ~68 GW; that is a different population from the
  {len(a15) + len(w15)} requests in this file, so the two are not differenced here.)
- **Withdrawn {RECENT_FROM_YEAR}–{THIS_YEAR} to date, both reports:** {wd_recent_all.net_mw.sum():,.0f} MW,
  of which {wd_recent_all.storage_mw.sum():,.0f} MW storage.
  (All-time since 2006, both reports: {pd.concat([pqw, w15]).net_mw.sum():,.0f} MW — a number that mostly describes
  dead wind and solar-era projects.)

## Official Cluster 16 POI statements (the layer no spreadsheet tool has)

{tbl(avail, ['poi_base','utility','c16_poi_status','c16_poi_note','legacy_active_mw','c15_active_mw'])}

The same notice says PG&E stations exceeding 63 kA short-circuit duty are restricted but does not name them, and that the
Transmission Interconnection Handbook will not reflect this "until updated, no ETA". Read the notice, not the handbook.

## Top nodes by total pipeline MW (legacy + C15)

{tbl(top, ['poi_base','county','utility','legacy_active_mw','c15_active_mw','operating_mw','wd_recent_mw','storage_churn','c15_survival'])}

## 2025 TPD allocation cycle by node — requested vs allocated vs denied (CAISO results xlsx, posted 2026-05-04)

{tbl(tpd_tbl, ['poi_base','county','utility','tpd25_projects','tpd25_req_mw','tpd25_alloc_mw','tpd25_unalloc_mw','tpd25_denied_mw','tpd25_denied_ppa_mw','tpd25_denied_D_mw','tpd24_fcdsa_projects'])}

"Denied" is MW refused outright (0 %); "unalloc" is requested minus allocated, so it also carries the remainder left by
partial allocations — quote that one for "what the developer did not get". A refusal is not one thing: CAISO allocates
by group — A = executed PPA (or LSE own load), B = shortlisted / negotiating a PPA, C = already operating, D = no PPA,
Section 8.9.2.3 path. A 0 % in group D is the expected result for an uncontracted project; a 0 % in group A or B
(`tpd25_denied_ppa_mw`) is a contracted project that did not get deliverability, and is the number to quote. Across the
2025 file: {tpd_grp}. These rows are joined through all three sheets
of the public report, so a node's TPD history can include requests whose project has since withdrawn
({wd_tpd_req:,.0f} MW requested / {wd_tpd_alloc:,.0f} MW allocated in the 2025 cycle across all nodes).
Allocation is CAISO's decision under Appendix DD; the file states no reason and neither does this table.

## Storage churn, {RECENT_FROM_YEAR}–{THIS_YEAR} to date (nodes with >300 MW storage surviving and >300 MW storage withdrawn)

{tbl(hot, ['poi_base','county','utility','pipeline_storage_mw','operating_storage_mw','wd_recent_storage_mw','storage_churn'])}

{whirl_txt}

## Withdrew after Phase II / Facilities Study results (public report; MW)

These developers had upgrade cost estimates in hand when they left. That is the closest thing to a cost signal in the file — it is still not a cause.

{tbl(post2, ['poi_base','county','utility','wd_post_phase2_mw','pipeline_mw','operating_mw'])}

## Local Capacity Areas — the Resource Adequacy geography (CAISO Final 2027 Local Capacity Technical Report)

For storage, location value is RA first and energy second, and local RA needs a POI inside a Local Capacity Area.
The report names only the substations that *delineate* each area ("X is out, Y is in"), so a node not listed here is
"not encoded", never "outside every area". Nodes the report places INSIDE an area, by pipeline MW:

{tbl(lcr_in, ['poi_base','county','utility','lcr_area','lcr_sub_area','legacy_active_mw','c15_active_mw','operating_mw','lcr_note'])}

Heavily queued nodes the report names as OUTSIDE an area boundary — bulk stations with no local RA value from that area:

{tbl(lcr_out, ['poi_base','county','utility','lcr_status','pipeline_mw','operating_mw','lcr_note'])}

## Cluster 15 nodes with little recent wreckage (<300 MW withdrawn since {RECENT_FROM_YEAR})

{tbl(clean, ['poi_base','county','utility','c15_active_mw','c15_fcds_req_mw','wd_recent_mw','legacy_active_mw','c16_poi_status'])}

## Cluster 15 survival by node (lowest first; >500 MW requested)

{tbl(survivors, ['poi_base','county','utility','c15_active_mw','c15_withdrawn_mw','c15_survival'])}

## Cluster 15 withdrawals by month

{w15.groupby(w15.withdrawn_date.dt.to_period('M')).net_mw.agg(['count','sum']).round(0).to_markdown()}

## Positions to audit before publishing a map (>500 MW, approximate or missing)

{tbl(approx, ['poi_base','county','pipeline_mw','geo_method','geo_score'])}

## Caveats (say these out loud to any reader)

1. POI strings are free text. `poi_geocode.csv` shows every match, score and method. `line-one-end` means the marker sits at one end of a line, not the tap.
2. Cluster 15 "deliverability" is *requested*, not allocated. TPD allocation is a separate CAISO process.
3. Withdrawal is not failure at the node, and the files give no reason beyond "IC Request". Do not attribute causes.
4. Nothing here is load-side. Data-center load interconnection is a utility process with no public queue.
5. Availability statements are encoded only where a source names the POI. Absence of a row is not availability.
"""
    (OUT / "node_watch.md").write_text(md)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    pq, c15 = load_projects()
    nodes = build_nodes(pq, c15)
    nodes = join_tpd(nodes, pq)
    # per-request rows for the node pages (written here, not in join_tpd, so tests never touch outputs/)
    tpd.node_rows(tpd.load_all(), pq).to_csv(OUT / "tpd_node_rows.csv", index=False)
    nodes = lcr.join(nodes)
    nodes = join_wdat(nodes)
    nodes = join_lmp(nodes)
    nodes = join_availability(nodes)
    nodes = geocode_nodes(nodes)
    nodes = eia860.join(nodes)          # needs positions, so after geocoding
    nodes = add_provenance(nodes, "publicqueuereport.xlsx+cluster15.xlsx",
                           str(pq["source_run_date"].iloc[0]) if "source_run_date" in pq else None)
    nodes.to_csv(OUT / "nodes.csv", index=False)
    write_map(nodes)
    write_node_watch(nodes, pq, c15)
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print(f"\n{len(nodes)} nodes; {(nodes.pipeline_mw > 0).sum()} with active pipeline")
    print(nodes.head(15)[["poi_base", "county", "utility", "legacy_active_mw", "c15_active_mw", "operating_mw",
                          "wd_recent_mw", "storage_churn", "c15_survival", "tpd25_req_mw", "tpd25_alloc_mw", "tpd25_denied_mw",
                          "c16_poi_status", "geo_method"]].to_string(index=False))
    print("\nwrote outputs/nodes.csv, poi_geocode.csv, nodes_map.html, node_watch.md")


if __name__ == "__main__":
    main()
