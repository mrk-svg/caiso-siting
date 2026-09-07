#!/usr/bin/env python3
"""
Node table: unify the Public Queue Report + Cluster 15 report per Point of
Interconnection, geocode POIs against OpenStreetMap substations, and emit a
Leaflet map + node_watch.md.

Inputs (all free):
  data/publicqueuereport.xlsx   CAISO public queue (Cluster 14 and earlier)
  data/cluster15.xlsx           CAISO Cluster 15 report
  data/osm_substations.csv      Overpass export: id,type,lat,lon,name,voltage,operator,substation

Outputs:
  outputs/nodes.csv             one row per POI with legacy/C15/withdrawn MW + lat/lon
  outputs/poi_geocode.csv       every POI string -> matched OSM substation + score (audit this!)
  outputs/nodes_map.html        interactive map (no dependencies beyond a browser)
  outputs/node_watch.md         the analysis draft

    python nodes.py
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

import caiso_queue
import cluster15

DATA = Path("data")
OUT = Path("outputs")

# ------------------------------------------------------------------ POI names

NOISE = re.compile(
    r"\b(SUBSTATION|SUB|SW STA|SWITCHING STATION|SWITCHING STA|SWITCHYARD|SWITCH|SW|STA|STATION|"
    r"PP|POWER PLANT|GENERATING STATION|GEN STA|BUS|TAP|LINE|SEGMENT|JUNCTION|JCT|"
    r"NO\.?\s*\d+|#\s*\d+|\d{2,3}\s*KV|\d{2,3}KV)\b"
)


def norm(name: str) -> str:
    s = str(name).upper()
    s = re.sub(r"\(.*?\)", " ", s)            # (SDGE) etc.
    s = NOISE.sub(" ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def endpoints(poi: str) -> list[str]:
    """'NORTH GILA - HOODOO WASH 500 kV' -> ['NORTH GILA', 'HOODOO WASH'].
    A POI on a line is geocoded to the midpoint of its two named ends."""
    base = re.sub(r"\(.*?\)", " ", str(poi).upper())
    base = re.sub(r"\d{2,3}\s*KV.*$", "", base)
    parts = [p for p in re.split(r"\s+-\s+|-(?=[A-Z])|\s+TO\s+", base) if p.strip()]
    parts = [norm(p) for p in parts]
    parts = [p for p in parts if len(p) >= 3]
    return parts[:2] if parts else [norm(poi)]


# ------------------------------------------------------------------ geocoding

def load_osm(path: Path) -> pd.DataFrame:
    osm = pd.read_csv(path, dtype=str, quotechar='"', on_bad_lines="skip")
    osm.columns = [c.strip().lstrip("@") for c in osm.columns]
    osm = osm.rename(columns={"id": "osm_id", "type": "osm_type"})
    osm["lat"] = pd.to_numeric(osm["lat"], errors="coerce")
    osm["lon"] = pd.to_numeric(osm["lon"], errors="coerce")
    osm = osm.dropna(subset=["lat", "lon"])
    osm = osm[osm["name"].notna() & (osm["name"].str.strip() != "")].copy()
    osm["key"] = osm["name"].map(norm)
    # max voltage in volts, used to prefer transmission-level matches
    osm["kv"] = osm["voltage"].fillna("").str.extract(r"(\d{4,6})", expand=False).astype(float) / 1000
    osm = osm[osm["key"] != ""]
    return osm.reset_index(drop=True)


class Geocoder:
    def __init__(self, osm: pd.DataFrame, overrides_path: Path = DATA / "poi_overrides.csv"):
        self.osm = osm
        # data/poi_overrides.csv: poi,lat,lon,note  — hand-verified coordinates for POIs
        # OSM lacks (Manning, Dry Lake, Trout Canyon, Moss Landing...). Wins over any match.
        self.overrides = {}
        if overrides_path.exists():
            ov = pd.read_csv(overrides_path, dtype=str, comment="#").dropna(subset=["poi", "lat", "lon"])
            for _, r in ov.iterrows():
                self.overrides[norm(r["poi"])] = dict(lat=float(r["lat"]), lon=float(r["lon"]), note=r.get("note", "manual"))
        self.by_key = {}
        for i, k in enumerate(osm["key"]):
            self.by_key.setdefault(k, []).append(i)
        self.keys = list(self.by_key)

    def _pick(self, idxs):
        # prefer the highest-voltage record when several substations share a name
        sub = self.osm.loc[idxs]
        return sub.sort_values("kv", ascending=False, na_position="last").iloc[0]

    def match(self, name: str):
        k = norm(name)
        if not k:
            return None, 0.0
        if k in self.by_key:
            return self._pick(self.by_key[k]), 1.0
        # token-containment first (WINDHUB vs WIND HUB, LOS BANOS vs LOS BANOS WEST)
        toks = set(k.split())
        cands = [kk for kk in self.keys if toks <= set(kk.split()) or set(kk.split()) <= toks]
        pool = cands if cands else self.keys
        best, score = None, 0.0
        for kk in pool:
            s = SequenceMatcher(None, k, kk).ratio()
            if s > score:
                best, score = kk, s
        # Fuzzy matches must share the first token: "MOSS LANDING" must not
        # resolve to "CROWS LANDING", nor "EAST COUNTY" to "EAST CITY".
        if best is None or score < 0.85 or best.split()[0] != k.split()[0]:
            return None, score
        return self._pick(self.by_key[best]), score

    def geocode_poi(self, poi: str):
        k = norm(poi)
        if k in self.overrides:
            o = self.overrides[k]
            return dict(lat=o["lat"], lon=o["lon"], osm_name=o.get("note", "manual"), score=1.0, method="override")
        whole, ws = self.match(poi)          # "VACA-DIXON" is one substation, not a line
        if whole is not None and ws == 1.0:
            return dict(lat=whole.lat, lon=whole.lon, osm_name=whole["name"], score=1.0, method="exact")
        ends = endpoints(poi)
        hits = [(self.match(e)) for e in ends]
        good = [(r, s) for r, s in hits if r is not None]
        if not good:
            return dict(lat=None, lon=None, osm_name=None, score=max(s for _, s in hits), method="none")
        if len(ends) == 2 and len(good) == 2:
            (a, sa), (b, sb) = good
            return dict(lat=(a.lat + b.lat) / 2, lon=(a.lon + b.lon) / 2,
                        osm_name=f"{a['name']} | {b['name']}", score=min(sa, sb), method="line-midpoint")
        r, s = good[0]
        if len(ends) == 2:  # a line POI where only one end resolved — flag it for audit
            return dict(lat=r.lat, lon=r.lon, osm_name=r["name"], score=round(s * 0.7, 2), method="line-one-end")
        return dict(lat=r.lat, lon=r.lon, osm_name=r["name"], score=s,
                    method="exact" if s == 1.0 else "fuzzy")


# ------------------------------------------------------------------ node table

def build_nodes() -> tuple[pd.DataFrame, pd.DataFrame]:
    pq = caiso_queue.load_all(DATA / "publicqueuereport.xlsx")
    c15 = cluster15.load(DATA / "cluster15.xlsx")

    # Both reports spell the same substation differently ("WHIRLWIND SUBSTATION" vs
    # "WHIRLWIND", "LOS BANOS 230 kV" vs "LOS BANOS SW STA"). Key on the normalized name.
    for df in (pq, c15):
        df["node_key"] = df["poi"].map(norm)
    key = ["node_key"]

    def agg(df, mask, prefix):
        sub = df[mask]
        return sub.groupby(key).agg(**{
            f"{prefix}_projects": ("project_name", "count"),
            f"{prefix}_mw": ("net_mw", "sum"),
            f"{prefix}_storage_mw": ("storage_mw", "sum"),
        })

    # representative label / county / utility per node (most common value across both reports)
    both = pd.concat([pq[["node_key", "poi_base", "county", "utility"]],
                      c15[["node_key", "poi_base", "county", "utility"]]])
    both = both[both.node_key != ""]
    labels = both.groupby("node_key").agg(
        poi_base=("poi_base", lambda s: s.mode().iloc[0]),
        county=("county", lambda s: s[s != ""].mode().iloc[0] if (s != "").any() else ""),
        utility=("utility", lambda s: s[s != ""].mode().iloc[0] if (s != "").any() else ""))

    legacy_active = agg(pq, pq.sheet_status == "ACTIVE", "legacy_active")
    legacy_wd = agg(pq, pq.sheet_status == "WITHDRAWN", "hist_withdrawn")
    completed = agg(pq, pq.sheet_status == "COMPLETED", "completed")
    c15_active = agg(c15, c15.sheet_status == "ACTIVE", "c15_active")
    c15_wd = agg(c15, c15.sheet_status == "WITHDRAWN", "c15_withdrawn")

    # deliverability requested in C15 at this node
    c15a = c15[c15.sheet_status == "ACTIVE"]
    fcds = c15a[c15a.deliverability.str.startswith("FULL")].groupby(key).net_mw.sum().rename("c15_fcds_req_mw")

    nodes = (legacy_active.join(c15_active, how="outer").join(legacy_wd, how="outer")
             .join(c15_wd, how="outer").join(completed, how="outer").join(fcds, how="outer")
             .fillna(0))
    nodes = labels.join(nodes, how="right").fillna({"poi_base": "", "county": "", "utility": ""}).reset_index()
    nodes = nodes[nodes.node_key != ""]
    nodes["pipeline_mw"] = nodes.legacy_active_mw + nodes.c15_active_mw
    nodes["operating_mw"] = nodes.completed_mw
    nodes["total_withdrawn_mw"] = nodes.hist_withdrawn_mw + nodes.c15_withdrawn_mw
    nodes["churn_ratio"] = (nodes.total_withdrawn_mw /
                            (nodes.pipeline_mw + nodes.operating_mw).replace(0, float("nan"))).round(2)
    nodes["c15_survival"] = (nodes.c15_active_mw /
                             (nodes.c15_active_mw + nodes.c15_withdrawn_mw).replace(0, float("nan"))).round(2)
    return nodes.sort_values("pipeline_mw", ascending=False).reset_index(drop=True), pq


def geocode_nodes(nodes: pd.DataFrame) -> pd.DataFrame:
    osm_path = DATA / "osm_substations.csv"
    if not osm_path.exists():
        print("no data/osm_substations.csv — skipping geocode")
        for c in ("lat", "lon", "osm_name", "geo_score", "geo_method"):
            nodes[c] = None
        return nodes
    gc = Geocoder(load_osm(osm_path))
    rows = []
    for nk, poi in nodes[["node_key", "poi_base"]].drop_duplicates("node_key").itertuples(index=False):
        r = gc.geocode_poi(poi)
        rows.append(dict(node_key=nk, poi_base=poi, lat=r["lat"], lon=r["lon"], osm_name=r["osm_name"],
                         geo_score=round(r["score"], 2), geo_method=r["method"]))
    geo = pd.DataFrame(rows)
    geo.to_csv(OUT / "poi_geocode.csv", index=False)
    nodes = nodes.merge(geo.drop(columns="poi_base"), on="node_key", how="left")
    matched = nodes.lat.notna()
    print(f"geocode: {matched.sum()}/{len(nodes)} POIs matched ({matched.mean():.0%}); "
          f"by MW: {nodes.loc[matched, 'pipeline_mw'].sum() / nodes.pipeline_mw.sum():.0%} of pipeline MW located")
    print(nodes.geo_method.value_counts().to_dict())
    return nodes


# ------------------------------------------------------------------ outputs

def write_map(nodes: pd.DataFrame) -> None:
    pts = nodes[nodes.lat.notna() & (nodes.pipeline_mw > 0)]
    feats = []
    for _, r in pts.iterrows():
        feats.append(dict(
            lat=r.lat, lon=r.lon, poi=r.poi_base, county=r.county, utility=r.utility,
            legacy=round(r.legacy_active_mw), c15=round(r.c15_active_mw), wd=round(r.total_withdrawn_mw),
            churn=None if pd.isna(r.churn_ratio) else r.churn_ratio,
            surv=None if pd.isna(r.c15_survival) else r.c15_survival,
            score=r.geo_score, method=r.geo_method, osm=r.osm_name))
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>CAISO interconnection nodes</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#m{{height:100%;margin:0;font-family:system-ui}} .lg{{background:#fff;padding:8px 10px;border-radius:6px;font-size:12px;line-height:1.5}}</style>
</head><body><div id="m"></div><script>
const pts={json.dumps(feats)};
const m=L.map('m').setView([36.3,-119.3],6);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'&copy; OpenStreetMap; data: CAISO public queue + Cluster 15 reports'}}).addTo(m);
const col=c=> c==null?'#888': c<0.5?'#2a9d8f': c<1.5?'#e9c46a':'#e63946';
for(const p of pts){{
  const mw=p.legacy+p.c15; const r=Math.max(4,Math.sqrt(mw)/2.2);
  L.circleMarker([p.lat,p.lon],{{radius:r,color:'#222',weight:1,fillColor:col(p.churn),fillOpacity:.75}})
   .bindPopup(`<b>${{p.poi}}</b><br>${{p.county}} / ${{p.utility}}<br>Legacy active: ${{p.legacy}} MW<br>Cluster 15 active: ${{p.c15}} MW<br>Withdrawn (all-time): ${{p.wd}} MW<br>Churn ratio: ${{p.churn??'n/a'}}<br>C15 survival: ${{p.surv??'n/a'}}<br><small>geocode: ${{p.method}} ${{p.score}} → ${{p.osm}}</small>`).addTo(m);
}}
const lg=L.control({{position:'bottomleft'}}); lg.onAdd=()=>{{const d=L.DomUtil.create('div','lg');
d.innerHTML='<b>Pipeline MW</b> = circle size<br><b>Churn</b> (withdrawn ÷ surviving MW)<br><span style="color:#2a9d8f">●</span> &lt;0.5 &nbsp;<span style="color:#e9c46a">●</span> 0.5–1.5 &nbsp;<span style="color:#e63946">●</span> &gt;1.5 &nbsp;<span style="color:#888">●</span> n/a';return d;}}; lg.addTo(m);
</script></body></html>"""
    (OUT / "nodes_map.html").write_text(html)


def write_node_watch(nodes: pd.DataFrame, pq: pd.DataFrame, c15: pd.DataFrame) -> None:
    a15 = c15[c15.sheet_status == "ACTIVE"]; w15 = c15[c15.sheet_status == "WITHDRAWN"]
    pqa = pq[pq.sheet_status == "ACTIVE"]
    top = nodes.head(12)
    grave = nodes[(nodes.total_withdrawn_mw > 2000)].sort_values("churn_ratio", ascending=False).head(8)
    clean = nodes[(nodes.c15_active_mw > 0) & (nodes.hist_withdrawn_mw < 500)].sort_values("c15_active_mw", ascending=False).head(8)
    survivors = nodes[nodes.c15_withdrawn_mw + nodes.c15_active_mw > 500].sort_values("c15_survival").head(8)

    def tbl(df, cols):
        return df[cols].round(0).to_markdown(index=False)

    md = f"""# CAISO Node Watch — draft {pd.Timestamp.today():%Y-%m-%d}

Sources: CAISO Public Queue Report (run date in file), CAISO Cluster 15 report (posted 2026-07-16),
OpenStreetMap substations (ODbL). All figures are net MW to grid as filed.

## The state of the queue in three numbers

- **Legacy pipeline (Cluster 14 and earlier):** {len(pqa)} active projects, {pqa.net_mw.sum():,.0f} MW,
  {pqa.has_storage.mean():.0%} with storage, {(pqa.ia_status == 'Executed').sum()} already under executed IAs.
- **Cluster 15 today:** {len(a15)} active projects, {a15.net_mw.sum():,.0f} MW ({a15.storage_mw.sum():,.0f} MW storage).
  {len(w15)} projects / {w15.net_mw.sum():,.0f} MW have withdrawn since intake. CAISO's July 2025 briefing put the
  studied set at 145 projects / ~68 GW; the cohort has since shed roughly {1 - a15.net_mw.sum()/68000:.0%} of its MW.
- **All-time withdrawn:** {(pq.sheet_status=='WITHDRAWN').sum()} projects / {pq[pq.sheet_status=='WITHDRAWN'].net_mw.sum():,.0f} MW.

## Where Cluster 15 capacity is still standing (requested service)

{a15.groupby('service_type').net_mw.agg(['count','sum']).round(0).to_markdown()}

## Top nodes by total pipeline MW (legacy + C15)

{tbl(top, ['poi_base','county','utility','legacy_active_mw','c15_active_mw','total_withdrawn_mw','churn_ratio','c15_survival'])}

## Graveyard nodes (>2 GW withdrawn, ranked by churn)

{tbl(grave, ['poi_base','county','utility','pipeline_mw','total_withdrawn_mw','churn_ratio'])}

## Cluster 15 nodes with little historical wreckage (<500 MW ever withdrawn)

{tbl(clean, ['poi_base','county','utility','c15_active_mw','c15_fcds_req_mw','hist_withdrawn_mw','legacy_active_mw'])}

## Cluster 15 survival by node (lowest first; >500 MW requested)

{tbl(survivors, ['poi_base','county','utility','c15_active_mw','c15_withdrawn_mw','c15_survival'])}

## Cluster 15 withdrawals by month

{w15.groupby(w15.withdrawn_date.dt.to_period('M')).net_mw.agg(['count','sum']).round(0).to_markdown()}

## Caveats (say these out loud to any reader)

1. POI strings are free text. `poi_geocode.csv` shows every match and its score; audit anything under 0.9.
2. Cluster 15 "deliverability" is *requested*, not allocated. TPD allocation is decided by CAISO's
   Transmission Plan Deliverability process; this file cannot tell you who gets it.
3. Withdrawal is not failure at the node — it is often a portfolio decision by the developer.
4. Nothing here is load-side. Data center load interconnection is a utility (PG&E/SCE/SDGE) process with no public queue.
"""
    (OUT / "node_watch.md").write_text(md)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    nodes, pq = build_nodes()
    c15 = cluster15.load(DATA / "cluster15.xlsx")
    nodes = geocode_nodes(nodes)
    nodes.to_csv(OUT / "nodes.csv", index=False)
    write_map(nodes)
    write_node_watch(nodes, pq, c15)
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print(f"\n{len(nodes)} nodes; {(nodes.pipeline_mw>0).sum()} with active pipeline")
    print("\nTop 15 nodes by pipeline MW")
    print(nodes.head(15)[["poi_base", "county", "utility", "legacy_active_mw", "c15_active_mw",
                          "total_withdrawn_mw", "churn_ratio", "c15_survival", "geo_method", "geo_score"]].to_string(index=False))
    print("\nwrote outputs/nodes.csv, poi_geocode.csv, nodes_map.html, node_watch.md")


if __name__ == "__main__":
    main()
