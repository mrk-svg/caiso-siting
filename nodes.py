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

Outputs:
  outputs/nodes.csv, poi_geocode.csv, nodes_map.html, node_watch.md

Metric definitions (read before quoting any of them):
  legacy_active_mw        active MW in the public report (C14 and earlier)
  c15_active_mw           active MW in the Cluster 15 report
  pipeline_mw             the two above
  operating_mw            completed MW in the public report
  wd_alltime_mw           every withdrawn MW since 2006 (includes dead wind/solar-era projects)
  wd_recent_mw            withdrawn in the last RECENT_YEARS years (both reports)
  wd_recent_storage_mw    the storage share of wd_recent_mw
  wd_post_phase2_mw       withdrew AFTER Phase II / Facilities Study results (public report only)
  storage_churn           wd_recent_storage_mw / (active + operating storage MW)   <- the one to quote
  churn_alltime           wd_alltime_mw / (pipeline + operating MW)                 <- historical color only
  c15_survival            c15_active / (c15_active + c15_withdrawn)
None of these say WHY anything withdrew. The files carry no reason beyond "IC Request".
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

import caiso_queue
import cluster15
from common import norm_poi, poi_endpoints

DATA = Path("data")
OUT = Path("outputs")
RECENT_YEARS = 5
THIS_YEAR = pd.Timestamp.today().year


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

    def _pick(self, idxs):
        return self.osm.loc[idxs].sort_values("kv", ascending=False, na_position="last").iloc[0]

    def match(self, name: str):
        k = norm_poi(name)
        if not k:
            return None, 0.0
        if k in self.by_key:
            return self._pick(self.by_key[k]), 1.0
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
        return self._pick(self.by_key[best]), score

    def geocode_poi(self, poi: str) -> dict:
        k = norm_poi(poi)
        if k in self.overrides:
            o = self.overrides[k]
            return dict(lat=o["lat"], lon=o["lon"], osm_name=o["note"],
                        score=0.8 if o["approx"] else 1.0, method="override-approx" if o["approx"] else "override")
        whole, ws = self.match(poi)                       # "VACA-DIXON" is one substation
        if whole is not None and ws == 1.0:
            return dict(lat=whole.lat, lon=whole.lon, osm_name=whole["name"], score=1.0, method="exact")
        ends = poi_endpoints(poi)
        # an override may exist for one endpoint (e.g. HARLAN in "MANNING-HARLAN")
        hits = []
        for e in ends:
            if e in self.overrides:
                o = self.overrides[e]
                hits.append((pd.Series(dict(lat=o["lat"], lon=o["lon"], name=o["note"])), 1.0))
            else:
                hits.append(self.match(e))
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
    recent = both["withdrawn_year"].fillna(0) >= THIS_YEAR - RECENT_YEARS
    wd = both["sheet_status"] == "WITHDRAWN"

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
    ]
    nodes = parts[0]
    for p in parts[1:]:
        nodes = nodes.join(p, how="outer")
    nodes = nodes.fillna(0)

    labels = both.groupby(key).agg(
        poi_base=("poi_base", lambda s: s.mode().iloc[0]),
        county=("county", lambda s: s[s != ""].mode().iloc[0] if (s != "").any() else ""),
        utility=("utility", lambda s: s[s != ""].mode().iloc[0] if (s != "").any() else ""))
    nodes = labels.join(nodes, how="right").fillna({"poi_base": "", "county": "", "utility": ""}).reset_index()
    nodes = nodes[nodes[key] != ""]

    nodes["pipeline_mw"] = nodes.legacy_active_mw + nodes.c15_active_mw
    nodes["pipeline_storage_mw"] = nodes.legacy_active_storage_mw + nodes.c15_active_storage_mw
    nz = lambda s: s.replace(0, float("nan"))
    nodes["storage_churn"] = (nodes.wd_recent_storage_mw /
                              nz(nodes.pipeline_storage_mw + nodes.operating_storage_mw)).round(2)
    nodes["churn_alltime"] = (nodes.wd_alltime_mw / nz(nodes.pipeline_mw + nodes.operating_mw)).round(2)
    nodes["c15_survival"] = (nodes.c15_active_mw / nz(nodes.c15_active_mw + nodes.c15_withdrawn_mw)).round(2)
    return nodes.sort_values("pipeline_mw", ascending=False).reset_index(drop=True)


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
    gc = Geocoder(load_osm(osm_path) if osm_path.exists() else pd.DataFrame(columns=["key", "name", "lat", "lon", "voltage"]))
    rows = []
    for nk, poi in nodes[["node_key", "poi_base"]].drop_duplicates("node_key").itertuples(index=False):
        r = gc.geocode_poi(poi)
        rows.append(dict(node_key=nk, poi_base=poi, lat=r["lat"], lon=r["lon"], osm_name=r["osm_name"],
                         geo_score=round(r["score"], 2), geo_method=r["method"]))
    geo = pd.DataFrame(rows)
    geo.to_csv(OUT / "poi_geocode.csv", index=False)
    nodes = nodes.merge(geo.drop(columns="poi_base"), on="node_key", how="left")
    located = nodes.lat.notna()
    print(f"geocode: {located.sum()}/{len(nodes)} nodes located ({located.mean():.0%}); "
          f"{nodes.loc[located, 'pipeline_mw'].sum() / nodes.pipeline_mw.sum():.0%} of pipeline MW; "
          f"methods {nodes.geo_method.value_counts().to_dict()}")
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
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>CAISO interconnection nodes</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#m{{height:100%;margin:0;font-family:system-ui}} .lg{{background:#fff;padding:8px 10px;border-radius:6px;font-size:12px;line-height:1.55;max-width:260px}}</style>
</head><body><div id="m"></div><script>
const pts={json.dumps(feats)};
const m=L.map('m').setView([36.3,-119.3],6);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'&copy; OpenStreetMap; data: CAISO public queue + Cluster 15 reports + CAISO POI notices'}}).addTo(m);
const col=c=> c==null?'#9a9a9a': c<0.25?'#2a9d8f': c<1?'#e9c46a':'#e63946';
for(const p of pts){{
  const mw=p.legacy+p.c15; const r=Math.max(4,Math.sqrt(mw)/2.2);
  const approx = p.method==='line-one-end' || p.method==='fuzzy' || p.method==='override-approx';
  const ring = p.st==='UNAVAILABLE'?'#000': p.st==='AVAILABLE'?'#1d4ed8':'#222';
  L.circleMarker([p.lat,p.lon],{{radius:r,color:ring,weight:p.st?3:1,dashArray:approx?'3,3':null,fillColor:col(p.sc),fillOpacity:approx?.25:.75}})
   .bindPopup(`<b>${{p.poi}}</b><br>${{p.county}} / ${{p.utility}}`+
     (p.st?`<br><b>C16 POI: ${{p.st}}</b> — ${{p.note}}`:'')+
     `<br>Legacy active ${{p.legacy}} MW · C15 active ${{p.c15}} MW · Operating ${{p.op}} MW`+
     `<br>Withdrawn last {RECENT_YEARS}y: ${{p.wdr}} MW (storage ${{p.wdrs}}) · after Phase II: ${{p.p2}} MW · all-time ${{p.wda}} MW`+
     `<br>Storage churn: ${{p.sc??'n/a'}} · C15 survival: ${{p.surv??'n/a'}}`+
     `<br><small>geocode ${{p.method}} ${{p.score}} → ${{p.osm}}${{approx?' — APPROXIMATE, not the tap point':''}}</small>`).addTo(m);
}}
const lg=L.control({{position:'bottomleft'}}); lg.onAdd=()=>{{const d=L.DomUtil.create('div','lg');
d.innerHTML='<b>Size</b> = pipeline MW (legacy + C15)<br><b>Fill</b> = storage churn, last {RECENT_YEARS}y (withdrawn storage ÷ surviving storage)<br>'+
'<span style="color:#2a9d8f">●</span> &lt;0.25 <span style="color:#e9c46a">●</span> 0.25–1 <span style="color:#e63946">●</span> &gt;1 <span style="color:#9a9a9a">●</span> n/a<br>'+
'<b>Ring</b>: <span style="color:#1d4ed8">blue</span> = stated AVAILABLE for C16, black = UNAVAILABLE<br>'+
'Dashed/pale = approximate position (line POI or fuzzy match)';return d;}}; lg.addTo(m);
</script></body></html>"""
    (OUT / "nodes_map.html").write_text(html)


def write_node_watch(nodes: pd.DataFrame, pq: pd.DataFrame, c15: pd.DataFrame) -> None:
    a15 = c15[c15.sheet_status == "ACTIVE"]; w15 = c15[c15.sheet_status == "WITHDRAWN"]
    pqa = pq[pq.sheet_status == "ACTIVE"]; pqw = pq[pq.sheet_status == "WITHDRAWN"]

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
    approx = nodes[(nodes.pipeline_mw > 500) & nodes.geo_method.isin(["line-one-end", "fuzzy", "override-approx", "none"])] \
        .sort_values("pipeline_mw", ascending=False)

    whirl = nodes[nodes.node_key == "WHIRLWIND"].iloc[0] if (nodes.node_key == "WHIRLWIND").any() else None
    whirl_txt = ""
    if whirl is not None:
        whirl_txt = (f"Example of why the window matters — Whirlwind (Kern, SCE): all-time churn {whirl.churn_alltime:.2f} "
                     f"looks like a graveyard; storage churn over the last {RECENT_YEARS} years is {whirl.storage_churn:.2f}, "
                     f"with {whirl.operating_mw:,.0f} MW operating and {whirl.pipeline_mw:,.0f} MW in pipeline. "
                     f"The old number describes 2008-era wind projects, not today's batteries.")

    md = f"""# CAISO Node Watch — draft {pd.Timestamp.today():%Y-%m-%d}

Sources: CAISO Public Queue Report (run date {pd.Timestamp.today():%Y-%m-%d}), CAISO Cluster 15 report (posted 2026-07-16),
CAISO notice "PG&E information on POI availability for Cluster 16" (2026-01-15), OpenStreetMap substations (ODbL).
All MW are net-to-grid as filed. No figure below states a *cause*; the CAISO files carry none.

## The state of the queue in three numbers

- **Legacy pipeline (Cluster 14 and earlier):** {len(pqa)} active projects, {pqa.net_mw.sum():,.0f} MW,
  {pqa.has_storage.mean():.0%} with storage, {(pqa.ia_status == 'Executed').sum()} already under executed IAs.
- **Cluster 15 today:** {len(a15)} active projects, {a15.net_mw.sum():,.0f} MW ({a15.storage_mw.sum():,.0f} MW storage);
  {len(w15)} projects / {w15.net_mw.sum():,.0f} MW withdrawn since intake. CAISO's July 2025 briefing put the studied set at
  145 projects / ~68 GW; the cohort has since shed roughly {1 - a15.net_mw.sum()/68000:.0%} of its MW.
- **Withdrawn, last {RECENT_YEARS} years (both reports):** {pd.concat([pqw, w15]).pipe(lambda d: d[d.withdrawn_year.fillna(0) >= THIS_YEAR - RECENT_YEARS]).net_mw.sum():,.0f} MW,
  of which {pd.concat([pqw, w15]).pipe(lambda d: d[d.withdrawn_year.fillna(0) >= THIS_YEAR - RECENT_YEARS]).storage_mw.sum():,.0f} MW storage.
  (All-time since 2006: {pqw.net_mw.sum():,.0f} MW — a number that mostly describes dead wind and solar-era projects.)

## Official Cluster 16 POI statements (the layer no spreadsheet tool has)

{tbl(avail, ['poi_base','utility','c16_poi_status','c16_poi_note','legacy_active_mw','c15_active_mw'])}

The same notice says PG&E stations exceeding 63 kA short-circuit duty are restricted but does not name them, and that the
Transmission Interconnection Handbook will not reflect this "until updated, no ETA". Read the notice, not the handbook.

## Top nodes by total pipeline MW (legacy + C15)

{tbl(top, ['poi_base','county','utility','legacy_active_mw','c15_active_mw','operating_mw','wd_recent_mw','storage_churn','c15_survival'])}

## Storage churn, last {RECENT_YEARS} years (nodes with >300 MW storage surviving and >300 MW storage withdrawn)

{tbl(hot, ['poi_base','county','utility','pipeline_storage_mw','operating_storage_mw','wd_recent_storage_mw','storage_churn'])}

{whirl_txt}

## Withdrew after Phase II / Facilities Study results (public report; MW)

These developers had upgrade cost estimates in hand when they left. That is the closest thing to a cost signal in the file — it is still not a cause.

{tbl(post2, ['poi_base','county','utility','wd_post_phase2_mw','pipeline_mw','operating_mw'])}

## Cluster 15 nodes with little recent wreckage (<300 MW withdrawn in {RECENT_YEARS} years)

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
    nodes = join_availability(nodes)
    nodes = geocode_nodes(nodes)
    nodes.to_csv(OUT / "nodes.csv", index=False)
    write_map(nodes)
    write_node_watch(nodes, pq, c15)
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print(f"\n{len(nodes)} nodes; {(nodes.pipeline_mw > 0).sum()} with active pipeline")
    print(nodes.head(15)[["poi_base", "county", "utility", "legacy_active_mw", "c15_active_mw", "operating_mw",
                          "wd_recent_mw", "wd_alltime_mw", "storage_churn", "churn_alltime", "c15_survival",
                          "c16_poi_status", "geo_method"]].to_string(index=False))
    print("\nwrote outputs/nodes.csv, poi_geocode.csv, nodes_map.html, node_watch.md")


if __name__ == "__main__":
    main()
