"""
Public GIS layers that need live network access (run from a normal terminal):

  caiso-siting layers lines            place line POIs on the actual CEC transmission-line geometry
                                       -> data/poi_lines.csv (cache read by `nodes`)
  caiso-siting layers screen NAME      Williamson Act + CEC siting screens for outputs/parcels_NAME.csv
                                       -> adds columns in place, writes parcels_NAME_screen.md
  caiso-siting layers screen --all     every outputs/parcels_*.csv

Sources (all public, no token; verified 2026-09-08):
  CEC  TransmissionLine_CEC  https://services3.arcgis.com/bWPjFyq029ChCGur/arcgis/rest/services/Transmission_Line/FeatureServer/2
       fields TLine_Name, kV, kV_Sort, Owner, Status, Circuit; polyline, Web Mercator, 2000/page
  CEC  siting screens (polygon, EPSG:3310, no attribute fields — presence only):
       BaseExclusions_Solar_v2, ProtectedAreas_Solar, Technoeconomic_Exclusion_Solar, Tribal_Lands, Critical_Habitat
  DOC  Williamson Act Enrollment 2025  https://gis.conservation.ca.gov/server/rest/services/DLRP/CaliforniaWilliamsonActEnrollment_2025/FeatureServer/9
       fields APN_Number, County_Cit, Year, Acreage, WA_Type (Prime | Nonprime | Nonrenewal | FSZ | Mixed)

Line placement rule: for a POI written as "A - B", find CEC lines whose TLine_Name contains both A and B
(highest kV wins), then place the node at the point on that line nearest the median position of the
project county's located nodes; if the county has none, the line's length-midpoint. Method `cec-line`,
score 0.9. Still an approximation of the tap — but on the right line, within a few km, instead of at one end.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

from .common import poi_endpoints
from .config import DATA, OUT

CEC = "https://services3.arcgis.com/bWPjFyq029ChCGur/arcgis/rest/services/"
LINE_LAYER = CEC + "Transmission_Line/FeatureServer/2"
SCREENS = {
    "excl_base_solar": CEC + "BaseExclusions_Solar_v2/FeatureServer/0",
    "excl_protected_solar": CEC + "ProtectedAreas_Solar/FeatureServer/0",
    "excl_technoeconomic_solar": CEC + "Technoeconomic_Exclusion_Solar/FeatureServer/0",
    "tribal_land": CEC + "Tribal_Lands/FeatureServer/0",
    "critical_habitat": CEC + "Critical_Habitat/FeatureServer/0",
}
WILLIAMSON = "https://gis.conservation.ca.gov/server/rest/services/DLRP/CaliforniaWilliamsonActEnrollment_2025/FeatureServer/9"
LINES_CACHE = DATA / "poi_lines.csv"


# ----------------------------------------------------------------- geometry (pure, tested)

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def polyline_midpoint(paths: list[list[list[float]]]) -> tuple[float, float]:
    """Length-weighted midpoint of an ESRI polyline ([[x,y],...] paths, x=lon, y=lat). Returns (lat, lon)."""
    segs = []
    for path in paths:
        for (x1, y1), (x2, y2) in zip(path, path[1:], strict=False):
            segs.append(((y1, x1), (y2, x2), haversine_km(y1, x1, y2, x2)))
    total = sum(s[2] for s in segs)
    if not segs or total == 0:
        y, x = paths[0][0][1], paths[0][0][0]
        return y, x
    half, acc = total / 2, 0.0
    for (a, b, d) in segs:
        if acc + d >= half:
            f = (half - acc) / d if d else 0
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        acc += d
    return segs[-1][1]


def nearest_vertex(paths, lat, lon) -> tuple[float, float, float]:
    """Vertex of the polyline nearest (lat, lon). Returns (lat, lon, km)."""
    best = (None, None, float("inf"))
    for path in paths:
        for x, y in path:
            d = haversine_km(lat, lon, y, x)
            if d < best[2]:
                best = (y, x, d)
    return best


def point_in_ring(lat, lon, ring) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if x > lon:
                inside = not inside
    return inside


def in_any(lat, lon, feats) -> bool:
    return any(any(point_in_ring(lat, lon, r) for r in f.get("geometry", {}).get("rings", [])) for f in feats)


def sql_escape(s: str) -> str:
    return s.replace("'", "''")


# ----------------------------------------------------------------- ArcGIS REST

def _get(url, params):
    import requests
    r = requests.get(url, params=params, timeout=90)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"{url}: {j['error']}")
    return j


def query(url: str, where: str = "1=1", geometry: dict | None = None, out_fields: str = "*",
          return_geometry: bool = True, distance_m: float | None = None) -> list[dict]:
    feats, offset = [], 0
    while True:
        p = dict(f="json", where=where, outFields=out_fields, returnGeometry=str(return_geometry).lower(),
                 outSR=4326, resultOffset=offset, resultRecordCount=1000)
        if geometry:
            g = dict(geometry)
            gtype = g.pop("_type", "esriGeometryPoint")
            p.update(geometry=json.dumps(g), geometryType=gtype, inSR=4326, spatialRel="esriSpatialRelIntersects")
            if distance_m:
                p.update(distance=distance_m, units="esriSRUnit_Meter")
        j = _get(f"{url}/query", p)
        feats += j.get("features", [])
        if not j.get("exceededTransferLimit"):
            return feats
        offset += len(j.get("features", []))


def envelope(lat, lon, km) -> dict:
    dlat = km / 111.0
    dlon = km / (111.0 * math.cos(math.radians(lat)))
    return {"xmin": lon - dlon, "ymin": lat - dlat, "xmax": lon + dlon, "ymax": lat + dlat,
            "spatialReference": {"wkid": 4326}, "_type": "esriGeometryEnvelope"}


# ----------------------------------------------------------------- lines

def find_line(a: str, b: str) -> dict | None:
    where = f"UPPER(TLine_Name) LIKE '%{sql_escape(a)}%' AND UPPER(TLine_Name) LIKE '%{sql_escape(b)}%'"
    feats = query(LINE_LAYER, where=where, out_fields="TLine_Name,kV,kV_Sort,Owner,Status,Circuit")
    if not feats:
        return None
    feats.sort(key=lambda f: -(f["attributes"].get("kV_Sort") or 0))
    return feats[0]


def place_lines(nodes: pd.DataFrame) -> pd.DataFrame:
    """Nodes whose POI names a line and whose position is not exact/override -> CEC line geometry."""
    loc = nodes[nodes.lat.notna() & ~nodes.geo_method.isin(["county-centroid", "none", "line-one-end"])].copy()
    loc["c1"] = loc.county.fillna("").str.split("/").str[0]
    cent = loc.groupby("c1").agg(lat=("lat", "median"), lon=("lon", "median"), n=("lat", "size"))
    cent = cent[cent.n >= 3]
    todo = nodes[nodes.geo_method.isin(["line-one-end", "none", "county-centroid"])]
    rows = []
    for r in todo.itertuples():
        ends = poi_endpoints(r.poi_base)
        if len(ends) != 2:
            continue
        try:
            f = find_line(ends[0], ends[1])
        except Exception as e:  # noqa: BLE001
            print(f"  {r.poi_base}: query failed ({e})", file=sys.stderr)
            continue
        if not f:
            continue
        paths = f["geometry"]["paths"]
        c1 = str(r.county).split("/")[0]
        if c1 in cent.index:
            lat, lon, _ = nearest_vertex(paths, cent.loc[c1, "lat"], cent.loc[c1, "lon"])
            how = "nearest-to-county"
        else:
            lat, lon = polyline_midpoint(paths)
            how = "length-midpoint"
        a = f["attributes"]
        rows.append(dict(node_key=r.node_key, lat=round(lat, 6), lon=round(lon, 6), method="cec-line", score=0.9,
                         tline_name=a.get("TLine_Name"), kv=a.get("kV"), owner=a.get("Owner"), placement=how,
                         source=LINE_LAYER))
        print(f"  {r.poi_base:40s} -> {a.get('TLine_Name')} {a.get('kV')} kV ({how})")
    out = pd.DataFrame(rows)
    if len(out):
        out.to_csv(LINES_CACHE, index=False)
    print(f"lines: {len(out)} of {len(todo)} candidate nodes placed on CEC line geometry -> {LINES_CACHE}")
    return out


# ----------------------------------------------------------------- screens

def screen_parcels(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, dtype={"apn": str})
    if df.empty or "lat" not in df:
        print(f"{csv.name}: nothing to screen")
        return df
    lat0, lon0 = df.lat.median(), df.lon.median()
    km = max(2.0, df.km_to_poi.max() + 1.0) if "km_to_poi" in df else 6.0
    env = envelope(lat0, lon0, km)
    # Williamson Act: by APN (exact) and by polygon (in case APN formats differ)
    apns = [a for a in df.apn.dropna().astype(str).unique()]
    wa_by_apn = {}
    for i in range(0, len(apns), 200):
        chunk = ",".join(f"'{sql_escape(a)}'" for a in apns[i:i + 200])
        for f in query(WILLIAMSON, where=f"APN_Number IN ({chunk})", out_fields="APN_Number,WA_Type,Acreage,Year", return_geometry=False):
            wa_by_apn[str(f["attributes"]["APN_Number"])] = f["attributes"].get("WA_Type") or "enrolled"
    wa_polys = query(WILLIAMSON, geometry=dict(env), out_fields="APN_Number,WA_Type")
    df["williamson_act"] = df.apn.astype(str).map(wa_by_apn).fillna("")
    miss = df.williamson_act == ""
    df.loc[miss, "williamson_act"] = [
        next((f["attributes"].get("WA_Type") or "enrolled" for f in wa_polys
              if any(point_in_ring(la, lo, r) for r in f.get("geometry", {}).get("rings", []))), "")
        for la, lo in zip(df.loc[miss, "lat"], df.loc[miss, "lon"], strict=True)]
    print(f"  williamson: {(df.williamson_act != '').sum()}/{len(df)} parcels enrolled ({len(wa_by_apn)} by APN)")
    for col, url in SCREENS.items():
        try:
            feats = query(url, geometry=dict(env), out_fields="OBJECTID")
        except Exception as e:  # noqa: BLE001
            print(f"  {col}: FAILED ({e})", file=sys.stderr)
            df[col] = ""
            continue
        df[col] = [in_any(la, lo, feats) for la, lo in zip(df.lat, df.lon, strict=True)]
        print(f"  {col}: {len(feats)} polygons in buffer; {df[col].sum()} parcels inside")
    df.to_csv(csv, index=False)
    name = csv.stem.replace("parcels_", "")
    lines = [f"# Siting screens — {name}", "",
             f"{len(df)} parcels. Williamson Act enrolment (DOC 2025 layer) and CEC siting screens (presence of the parcel centroid inside a screen polygon).",
             "", "| screen | parcels flagged | acres flagged |", "|---|---:|---:|"]
    lines.append(f"| Williamson Act (any type) | {(df.williamson_act != '').sum()} | {df.loc[df.williamson_act != '', 'acres'].sum():,.0f} |")
    for t in sorted(df.williamson_act[df.williamson_act != ""].unique()):
        lines.append(f"| &nbsp;&nbsp;{t} | {(df.williamson_act == t).sum()} | {df.loc[df.williamson_act == t, 'acres'].sum():,.0f} |")
    for col in SCREENS:
        if col in df and df[col].dtype == bool:
            lines.append(f"| {col} | {int(df[col].sum())} | {df.loc[df[col], 'acres'].sum():,.0f} |")
    clean = df[(df.williamson_act == "") & ~df[[c for c in SCREENS if c in df and df[c].dtype == bool]].any(axis=1)] if any(c in df for c in SCREENS) else df
    lines += ["", f"**Parcels with no flag: {len(clean)} ({clean.acres.sum():,.0f} ac)** — not 'de-risked'; unflagged by these five public layers only.", "",
              "_Williamson Act contracts restrict conversion for the contract term (10–20 yr, longer under FSZ); Nonrenewal means the clock is running. "
              "CEC screens are the CPUC IRP busbar-mapping exclusion set, provided 'as is'. Sources listed in layers.py._"]
    (OUT / f"parcels_{name}_screen.md").write_text("\n".join(lines))
    print(f"wrote {csv.name} (+{1 + len(SCREENS)} columns) and parcels_{name}_screen.md")
    return df


# ----------------------------------------------------------------- cli

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lines", help="place line POIs on CEC transmission-line geometry")
    s = sub.add_parser("screen", help="Williamson Act + CEC screens for a parcels csv")
    s.add_argument("name", nargs="?")
    s.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.cmd == "lines":
        nodes = pd.read_csv(OUT / "nodes.csv")
        place_lines(nodes)
        print("now re-run `caiso-siting nodes` to pick up data/poi_lines.csv")
    else:
        files = sorted(OUT.glob("parcels_*.csv")) if args.all else [OUT / f"parcels_{args.name}.csv"]
        files = [f for f in files if not f.name.endswith("_screen.csv")]
        if not files or not files[0].exists():
            sys.exit("no parcels csv found — run `caiso-siting parcels ...` first")
        for f in files:
            print(f.name)
            screen_parcels(f)


if __name__ == "__main__":
    main()
