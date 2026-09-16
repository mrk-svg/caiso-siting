#!/usr/bin/env python3
"""
Parcel and zoning context around a POI, from public county ArcGIS REST services.

    python3 parcels.py "DRY LAKE SW STA" --km 5
    python3 parcels.py --all-available --km 5      # every node with c16_poi_status == AVAILABLE
    python3 parcels.py --lat 35.7539 --lon -119.7446 --km 3 --name dry_lake

Writes outputs/parcels_<name>.csv (one row per parcel) and outputs/parcels_<name>_summary.md.

Needs normal internet access (run from your own terminal, not a sandboxed shell).
Only pandas + requests.

Layer registry — add a county by adding an entry. Only public, no-token services.
Verified 2026-09-07 with live queries:
  Kings parcels: 40 parcels within 5 km of Dry Lake, all AG_IND=Y, 160-320 ac sections.
  Kern zoning:   Bitterwater 5 km -> 'A' Exclusive Agriculture + 'See South Kern Industrial SP'.
Not available publicly (as of 2026-09-07): Kern countywide parcels (Assessor sells them), Fresno County parcels REST.
"""
from __future__ import annotations

import argparse
import math
import sys

import pandas as pd
import requests

from .common import norm_poi
from .config import OUT, csv_safe

LAYERS = {
    # county: {kind: (url, fields, label_field)}
    "KINGS": {
        "parcels": ("https://services3.arcgis.com/24gLq1DBBzDfd0cZ/arcgis/rest/services/Parcels/FeatureServer/0",
                    "APN,ACRES,AG_IND,COMMUNITY,DES_TOWNSH,DES_RANGE", "APN"),
        "general_plan": ("https://services3.arcgis.com/24gLq1DBBzDfd0cZ/arcgis/rest/services/General_Plan_Public/FeatureServer/0",
                         "GP,GP_DES,TYPE,ACRES", "GP_DES"),
    },
    "KERN": {
        "zoning": ("https://services5.arcgis.com/Y8jwjGUWbRjuqpG5/arcgis/rest/services/Kern_County_Zoning/FeatureServer/0",
                   "Zn_Cd1,Comb_Zn,Dscrptn,Case_Num", "Dscrptn"),
    },
}

# Which counties to query for a point. The proposed Dry Lake station sits on the Kings/Kern line,
# so query both; a wrong county simply returns zero features.
COUNTIES_FOR_POINT = ["KINGS", "KERN"]


def query(url: str, lat: float, lon: float, meters: float, fields: str, geometry: bool) -> list[dict]:
    feats, offset = [], 0
    while True:
        params = dict(f="json", where="1=1", geometry=f"{lon},{lat}", geometryType="esriGeometryPoint", inSR=4326,
                      spatialRel="esriSpatialRelIntersects", distance=meters, units="esriSRUnit_Meter",
                      outFields=fields, returnGeometry=str(geometry).lower(), outSR=4326,
                      resultOffset=offset, resultRecordCount=1000)
        r = requests.get(f"{url}/query", params=params, timeout=60)
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            raise RuntimeError(f"{url}: {j['error']}")
        feats += j.get("features", [])
        if not j.get("exceededTransferLimit"):
            break
        offset += len(j.get("features", []))
    return feats


def centroid(rings) -> tuple[float, float]:
    xs = [p[0] for ring in rings for p in ring]
    ys = [p[1] for ring in rings for p in ring]
    return sum(ys) / len(ys), sum(xs) / len(xs)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def point_in_ring(lat, lon, ring) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if x > lon:
                inside = not inside
    return inside


def run(name: str, lat: float, lon: float, km: float) -> None:
    OUT.mkdir(exist_ok=True)
    meters = km * 1000
    parcels, overlays = [], {}
    for county in COUNTIES_FOR_POINT:
        for kind, (url, fields, label) in LAYERS.get(county, {}).items():
            try:
                feats = query(url, lat, lon, meters, fields, geometry=True)
            except Exception as e:  # noqa: BLE001
                print(f"  {county}/{kind}: FAILED ({e})", file=sys.stderr)
                continue
            print(f"  {county}/{kind}: {len(feats)} features within {km} km")
            if kind == "parcels":
                for f in feats:
                    a = f["attributes"]
                    rings = f.get("geometry", {}).get("rings", [])
                    clat, clon = centroid(rings) if rings else (None, None)
                    parcels.append(dict(county=county, apn=a.get("APN"), acres=a.get("ACRES"), ag=a.get("AG_IND"),
                                        community=(a.get("COMMUNITY") or "").strip(), township=a.get("DES_TOWNSH"),
                                        range_=a.get("DES_RANGE"), lat=clat, lon=clon,
                                        km_to_poi=round(haversine_km(lat, lon, clat, clon), 2) if clat else None,
                                        _rings=rings))
            else:
                overlays[(county, kind)] = [(f["attributes"], f.get("geometry", {}).get("rings", []), label) for f in feats]

    df = pd.DataFrame(parcels)
    # tag each parcel with the zoning / general-plan polygon containing its centroid
    for (county, kind), feats in overlays.items():
        col = f"{county.lower()}_{kind}"
        vals = []
        for _, p in df.iterrows():
            hit = ""
            if p.lat is not None:
                for attrs, rings, label in feats:
                    if any(point_in_ring(p.lat, p.lon, ring) for ring in rings):
                        hit = str(attrs.get(label) or attrs.get("Comb_Zn") or attrs.get("GP") or "").strip()
                        break
            vals.append(hit)
        if len(df):
            df[col] = vals

    if len(df):
        df = df.drop(columns="_rings").sort_values("km_to_poi")
        csv_safe(df).to_csv(OUT / f"parcels_{name}.csv", index=False)

    lines = [f"# Parcels within {km} km of {name} ({lat:.5f}, {lon:.5f})", ""]
    if len(df):
        lines += [f"- {len(df)} parcels, {df.acres.sum():,.0f} acres total; {(df.ag == 'Y').mean():.0%} flagged agricultural",
                  f"- ≥160 ac parcels: {(df.acres >= 160).sum()}  (a 4-hour 200 MW BESS needs roughly 10–20 ac; a 500 MW solar+storage hybrid 2,500–4,000 ac)",
                  f"- nearest parcel {df.km_to_poi.min():.2f} km, median {df.km_to_poi.median():.2f} km", ""]
        for col in [c for c in df.columns if c.endswith(("_zoning", "_general_plan"))]:
            lines += [f"## {col.replace('_', ' ')} (by parcel count)", "",
                      df[col].replace("", "—").value_counts().rename_axis(col).reset_index(name="parcels").to_markdown(index=False), ""]
        lines += ["## Largest parcels", "",
                  df.nlargest(15, "acres")[[c for c in ("county", "apn", "acres", "ag", "km_to_poi") if c in df] +
                                          [c for c in df.columns if c.endswith(("_zoning", "_general_plan"))]].to_markdown(index=False), ""]
    else:
        lines.append("No parcel layer returned features — check COUNTIES_FOR_POINT and LAYERS for this location.")
    for (county, kind), feats in overlays.items():
        if kind != "parcels" and not len(df):
            codes = pd.Series([str(a.get(lbl) or a.get("Comb_Zn") or "").strip() for a, _, lbl in feats]).value_counts()
            lines += [f"## {county} {kind} polygons intersecting the buffer", "", codes.to_markdown(), ""]
    lines += ["", "_Owner names are not read or published by this project - a project policy, not a "
                  "statutory requirement; California assessor records are generally public. "
                  "Source layers listed in parcels.py._"]
    (OUT / f"parcels_{name}_summary.md").write_text("\n".join(lines))
    print(f"wrote outputs/parcels_{name}.csv and _summary.md")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("poi", nargs="?", help="POI label as in outputs/nodes.csv (needs lat/lon there)")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--name")
    ap.add_argument("--km", type=float, default=5)
    ap.add_argument("--all-available", action="store_true", help="every node with c16_poi_status == AVAILABLE")
    args = ap.parse_args()

    targets = []
    if args.lat is not None and args.lon is not None:
        targets.append((args.name or f"{args.lat}_{args.lon}", args.lat, args.lon))
    else:
        nodes = pd.read_csv(OUT / "nodes.csv")
        if args.all_available:
            sel = nodes[(nodes.c16_poi_status.fillna("") == "AVAILABLE") & nodes.lat.notna()]
        elif args.poi:
            sel = nodes[nodes.node_key == norm_poi(args.poi)]
            if sel.empty or sel.lat.isna().all():
                sys.exit(f"{args.poi}: not in nodes.csv or not located (add to data/poi_overrides.csv)")
        else:
            ap.error("give a POI, --lat/--lon, or --all-available")
        targets = [(r.node_key.lower().replace(" ", "_"), r.lat, r.lon) for r in sel.itertuples()]

    for name, lat, lon in targets:
        print(f"{name}: {lat:.5f}, {lon:.5f}, {args.km} km")
        run(name, lat, lon, args.km)


if __name__ == "__main__":
    main()
