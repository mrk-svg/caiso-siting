"""nodes.py: geocoder matching rules, county-centroid fallback, availability join, and the
node table built from the real reports."""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from caiso_siting import nodes
from caiso_siting.common import norm_poi

# ------------------------------------------------------------------- fixtures


def osm_frame(rows) -> pd.DataFrame:
    """Tiny frame shaped like load_osm output: key,name,lat,lon,voltage,kv (RangeIndex matters:
    Geocoder indexes by position)."""
    df = pd.DataFrame(rows, columns=["name", "lat", "lon", "kv"])
    df["voltage"] = (df.kv * 1000).astype("Int64").astype(str)
    df["key"] = df.name.map(norm_poi)
    return df[["key", "name", "lat", "lon", "voltage", "kv"]].reset_index(drop=True)


OSM_ROWS = [
    ("Whirlwind Substation", 34.90, -118.40, 66.0),     # lower-kV duplicate
    ("Whirlwind Substation", 34.91, -118.41, 230.0),    # the one _pick must choose
    ("Crows Landing", 37.40, -121.05, 115.0),
    ("Ross Landing", 37.50, -121.10, 115.0),            # ratio vs MOSS LANDING >= .85, first token differs
    ("East City", 32.70, -116.90, 69.0),
    ("Vaca-Dixon", 38.40, -121.90, 500.0),              # the line-looking name that is one substation
    ("North Gila", 32.70, -114.50, 500.0),
    ("Hoodoo Wash", 32.90, -114.10, 500.0),
    ("Colorado River", 33.70, -114.60, 500.0),
    ("Diablo Canyon", 35.21, -120.85, 500.0),
    ("Manning", 36.30, -120.30, 500.0),
]


@pytest.fixture
def osm() -> pd.DataFrame:
    return osm_frame(OSM_ROWS)


@pytest.fixture
def gc(osm, tmp_path) -> nodes.Geocoder:
    return nodes.Geocoder(osm, overrides_path=tmp_path / "no_overrides.csv")


def write_overrides(path: Path, rows) -> Path:
    lines = ["# hand-verified", "poi,lat,lon,approx,note"] + [",".join(map(str, r)) for r in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


# ------------------------------------------------------------------- load_osm

def test_load_osm_parses_overpass_export(tmp_path):
    p = tmp_path / "osm.csv"
    p.write_text(
        "@id,@type,@lat,@lon,name,voltage,operator,substation\n"
        "1,node,35.1,-118.1,Whirlwind Substation,230000;66000,SCE,transmission\n"
        "2,node,35.2,-118.2,,115000,,\n"                     # blank name -> dropped
        "3,way,bad,-118.3,Vincent,500000,,\n"                 # bad lat -> dropped
        "4,node,35.4,-118.4,Unnamed 230 kV,,,\n"              # voltage token stripped from the key
        "5,node,35.5,-118.5,Gates Substation,,,\n"            # no voltage -> kv NaN
    )
    osm = nodes.load_osm(p)
    assert list(osm.index) == list(range(len(osm)))
    assert {"key", "name", "lat", "lon", "voltage", "kv", "osm_id", "osm_type"} <= set(osm.columns)
    by = osm.set_index("name")
    assert by.loc["Whirlwind Substation", "key"] == "WHIRLWIND"
    assert by.loc["Whirlwind Substation", "kv"] == 230.0            # first 4-6 digit voltage
    assert pd.isna(by.loc["Gates Substation", "kv"])
    assert "Vincent" not in by.index
    assert by.loc["Unnamed 230 kV", "key"] == "UNNAMED"
    assert (osm.key != "").all()
    assert osm.lat.dtype == float


# ----------------------------------------------------------- Geocoder.match

def test_exact_match_wins_and_picks_highest_kv(gc):
    rec, score = gc.match("WHIRLWIND SUBSTATION 230 kV")
    assert score == 1.0
    assert rec.kv == 230.0 and rec.lat == 34.91
    for spelling in ("Whirlwind", "WHIRLWIND SUB", "whirlwind switching station"):
        assert gc.match(spelling)[1] == 1.0


def test_fuzzy_requires_same_first_token(gc):
    # ROSS LANDING scores >= .85 against MOSS LANDING but starts with a different token
    assert SequenceMatcher(None, "MOSS LANDING", "ROSS LANDING").ratio() >= 0.85
    rec, score = gc.match("MOSS LANDING PP 115 kV")
    assert rec is None and score >= 0.85
    # and CROWS LANDING never matches either
    assert gc.match("MOSS LANDING")[0] is None


def test_moss_landing_never_matches_crows_landing(tmp_path):
    g = nodes.Geocoder(osm_frame([("Crows Landing", 37.4, -121.05, 115.0)]), tmp_path / "none.csv")
    rec, score = g.match("MOSS LANDING")
    assert rec is None
    assert g.geocode_poi("MOSS LANDING PP 115 kV")["method"] == "none"


def test_east_county_never_matches_east_city(gc):
    rec, score = gc.match("EAST COUNTY SUBSTATION")
    assert rec is None and score < 0.85           # same first token, but below the score floor
    assert gc.geocode_poi("EAST COUNTY SUBSTATION 230 kV")["method"] == "none"


def test_fuzzy_match_accepted_above_floor_with_same_first_token(gc):
    rec, score = gc.match("DIABLO CANYONS")
    assert rec is not None and rec["name"] == "Diablo Canyon"
    assert 0.85 <= score < 1.0
    r = gc.geocode_poi("DIABLO CANYONS 500 kV")
    assert r["method"] == "fuzzy" and r["score"] == score and r["lat"] == 35.21


def test_empty_name_returns_nothing(gc):
    assert gc.match("") == (None, 0.0)
    assert gc.match("230 kV") == (None, 0.0)


# ------------------------------------------------------- Geocoder.geocode_poi

def test_geocode_exact_substation(gc):
    r = gc.geocode_poi("WHIRLWIND SUBSTATION 230 kV")
    assert r == dict(lat=34.91, lon=-118.41, osm_name="Whirlwind Substation", score=1.0, method="exact")


def test_override_beats_osm(osm, tmp_path):
    ov = write_overrides(tmp_path / "ov.csv", [("Whirlwind 230 kV", 34.95, -118.45, "no", "SCE one-line")])
    g = nodes.Geocoder(osm, overrides_path=ov)
    r = g.geocode_poi("WHIRLWIND SUBSTATION 230 kV")
    assert r["method"] == "override" and r["score"] == 1.0
    assert (r["lat"], r["lon"]) == (34.95, -118.45)
    assert r["osm_name"] == "SCE one-line"


def test_override_approx_flag(osm, tmp_path):
    ov = write_overrides(tmp_path / "ov.csv", [("TROUT CANYON", 36.1, -115.5, "yes", "plant centroid")])
    g = nodes.Geocoder(osm, overrides_path=ov)
    r = g.geocode_poi("TROUT CANYON 230 kV")
    assert r["method"] == "override-approx" and r["score"] == 0.8
    assert (r["lat"], r["lon"]) == (36.1, -115.5)


def test_override_rows_with_missing_coords_are_ignored(osm, tmp_path):
    ov = tmp_path / "ov.csv"
    ov.write_text("poi,lat,lon,approx,note\nWHIRLWIND,,,no,unknown\n")
    g = nodes.Geocoder(osm, overrides_path=ov)
    assert g.overrides == {}
    assert g.geocode_poi("WHIRLWIND")["method"] == "exact"


def test_vaca_dixon_resolves_as_one_substation_when_present_whole(gc):
    r = gc.geocode_poi("VACA-DIXON 230 kV")
    assert r["method"] == "exact" and r["score"] == 1.0
    assert r["osm_name"] == "Vaca-Dixon" and (r["lat"], r["lon"]) == (38.40, -121.90)


def test_vaca_dixon_falls_back_to_midpoint_when_only_ends_exist(tmp_path):
    g = nodes.Geocoder(osm_frame([("Vaca", 38.0, -122.0, 230.0), ("Dixon", 38.4, -121.8, 230.0)]),
                       tmp_path / "none.csv")
    r = g.geocode_poi("VACA-DIXON 230 kV")
    assert r["method"] == "line-midpoint"
    assert (r["lat"], r["lon"]) == pytest.approx((38.2, -121.9))


def test_line_with_both_ends_gives_midpoint(gc):
    r = gc.geocode_poi("NORTH GILA - HOODOO WASH 500 kV")
    assert r["method"] == "line-midpoint" and r["score"] == 1.0
    assert (r["lat"], r["lon"]) == pytest.approx((32.80, -114.30))
    assert r["osm_name"] == "North Gila | Hoodoo Wash"


def test_line_with_one_end_scores_point_seven(gc):
    r = gc.geocode_poi("DELANEY-COLORADO RIVER 500 kV")
    assert r["method"] == "line-one-end"
    assert r["score"] == pytest.approx(0.7)              # 1.0 * 0.7, rounded to 2 dp
    assert (r["lat"], r["lon"]) == (33.70, -114.60)
    assert r["osm_name"] == "Colorado River"


def test_line_endpoint_can_come_from_override(osm, tmp_path):
    ov = write_overrides(tmp_path / "ov.csv", [("HARLAN SW STA", 36.42, -120.41, "no", "CAISO notice")])
    g = nodes.Geocoder(osm, overrides_path=ov)
    r = g.geocode_poi("MANNING-HARLAN 500 kV")
    assert r["method"] == "line-midpoint"
    assert (r["lat"], r["lon"]) == pytest.approx(((36.30 + 36.42) / 2, (-120.30 + -120.41) / 2))
    assert r["osm_name"] == "Manning | CAISO notice"


def test_unresolvable_poi_reports_none_with_best_score(gc):
    r = gc.geocode_poi("ZZYZX ROAD 115 kV")
    assert r["method"] == "none" and r["lat"] is None and r["lon"] is None
    assert 0.0 <= r["score"] < 0.85


# ------------------------------------------------------ county_centroid_fallback

def node_frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["node_key", "county", "lat", "lon", "geo_method", "geo_score",
                                     "osm_name", "pipeline_mw"])
    return df


def test_county_centroid_fallback(capsys):
    n = node_frame([
        ("A", "KERN", 35.0, -118.0, "exact", 1.0, "a", 100),
        ("B", "KERN", 36.0, -119.0, "fuzzy", 0.9, "b", 100),
        ("C", "KERN/LOS ANGELES", 37.0, -120.0, "exact", 1.0, "c", 100),   # counts toward KERN (first county)
        ("D", "KERN/KINGS", np.nan, np.nan, "none", 0.0, None, 500),       # -> KERN centroid
        ("E", "KINGS", 36.1, -119.9, "exact", 1.0, "e", 10),
        ("F", "KINGS", 36.2, -119.8, "exact", 1.0, "f", 10),
        ("G", "KINGS", np.nan, np.nan, "none", 0.0, None, 50),             # only 2 located -> stays NaN
        ("H", "", np.nan, np.nan, "none", 0.0, None, 5),
    ])
    out = nodes.county_centroid_fallback(n)
    d = out.set_index("node_key").loc["D"]
    assert d.geo_method == "county-centroid" and d.geo_score == 0.3
    assert (d.lat, d.lon) == (36.0, -119.0)                       # median of the three KERN nodes
    assert d.osm_name == "median of located nodes in KERN"
    g = out.set_index("node_key").loc["G"]
    assert pd.isna(g.lat) and g.geo_method == "none"
    assert pd.isna(out.set_index("node_key").loc["H", "lat"])
    # located nodes untouched
    assert out.set_index("node_key").loc["A", "geo_method"] == "exact"
    assert "1 nodes placed at county centroids (500 MW)" in capsys.readouterr().out


def test_county_centroid_ignores_prior_centroids_as_sources():
    n = node_frame([
        ("A", "KERN", 35.0, -118.0, "county-centroid", 0.3, "x", 1),
        ("B", "KERN", 35.0, -118.0, "county-centroid", 0.3, "x", 1),
        ("C", "KERN", 35.0, -118.0, "county-centroid", 0.3, "x", 1),
        ("D", "KERN", np.nan, np.nan, "none", 0.0, None, 1),
    ])
    out = nodes.county_centroid_fallback(n)
    assert pd.isna(out.set_index("node_key").loc["D", "lat"])


# ------------------------------------------------------------ join_availability

def test_join_availability_latest_statement_wins(monkeypatch, tmp_path, capsys):
    (tmp_path / "poi_availability.csv").write_text(
        "# comment line\n"
        "poi,utility,status,note,source,date\n"
        "Whirlwind 230 kV,SCE,UNAVAILABLE,old note,src,2025-06-01\n"
        "WHIRLWIND SUBSTATION,SCE,AVAILABLE,new note,src,2026-01-15\n"
        "DRY LAKE SW STA,PGAE,AVAILABLE,new station,src,2026-01-15\n"
    )
    monkeypatch.setattr(nodes, "DATA", tmp_path)
    n = pd.DataFrame({"node_key": ["WHIRLWIND", "VINCENT"], "poi_base": ["WHIRLWIND SUBSTATION", "VINCENT"]})
    out = nodes.join_availability(n)
    assert out.c16_poi_status.tolist() == ["AVAILABLE", ""]
    assert out.c16_poi_note.tolist() == ["new note [2026-01-15]", ""]
    assert "1 nodes carry an official C16 POI statement" in capsys.readouterr().out


def test_join_availability_without_file(monkeypatch, tmp_path):
    monkeypatch.setattr(nodes, "DATA", tmp_path)
    out = nodes.join_availability(pd.DataFrame({"node_key": ["X"], "poi_base": ["X"]}))
    assert out.c16_poi_status.tolist() == [""] and out.c16_poi_note.tolist() == [""]


# ---------------------------------------------------------------- geocode_nodes

def test_geocode_nodes_writes_csv_to_out(monkeypatch, tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    data.mkdir()
    out.mkdir()
    (data / "osm_substations.csv").write_text(
        "@id,@type,@lat,@lon,name,voltage,operator,substation\n"
        "1,node,34.91,-118.41,Whirlwind Substation,230000,SCE,\n"
        "2,node,32.70,-114.50,North Gila,500000,,\n"
    )
    write_overrides(data / "poi_overrides.csv", [("VINCENT", 34.5, -118.1, "yes", "approx")])
    monkeypatch.setattr(nodes, "DATA", data)
    monkeypatch.setattr(nodes, "OUT", out)
    # geocode_nodes builds Geocoder(...) without an overrides path, so the default — bound to the
    # real DATA at import time — is what it reads; redirect that default too.
    monkeypatch.setattr(nodes.Geocoder.__init__, "__defaults__", (data / "poi_overrides.csv",))
    n = pd.DataFrame({
        "node_key": ["WHIRLWIND", "VINCENT", "NORTH GILA HOODOO WASH", "NOWHERE"],
        "poi_base": ["WHIRLWIND SUBSTATION", "VINCENT", "NORTH GILA - HOODOO WASH", "NOWHERE"],
        "county": ["KERN", "LOS ANGELES", "YUMA", "KERN"],
        "pipeline_mw": [100.0, 50.0, 25.0, 10.0],
    })
    geo = nodes.geocode_nodes(n).set_index("node_key")
    assert geo.geo_method.to_dict() == {"WHIRLWIND": "exact", "VINCENT": "override-approx",
                                        "NORTH GILA HOODOO WASH": "line-one-end", "NOWHERE": "none"}
    assert geo.loc["NORTH GILA HOODOO WASH", "geo_score"] == 0.7
    csv = pd.read_csv(out / "poi_geocode.csv")
    assert list(csv.columns) == ["node_key", "poi_base", "lat", "lon", "osm_name", "geo_score", "geo_method"]
    assert len(csv) == 4


# ------------------------------------------------------------------ build_nodes

def project_rows(rows) -> pd.DataFrame:
    cols = ["node_key", "poi_base", "county", "utility", "project_name", "net_mw", "storage_mw",
            "sheet_status", "withdrawn_year", "withdrew_post_phase2", "deliverability"]
    df = pd.DataFrame(rows, columns=cols)
    df["withdrawn_year"] = df.withdrawn_year.astype(float)
    return df


def test_build_nodes_synthetic():
    this = nodes.THIS_YEAR
    pq = project_rows([
        ("WHIRLWIND", "WHIRLWIND SUBSTATION", "KERN", "SCE", "p1", 200, 150, "ACTIVE", np.nan, False, "FULL CAPACITY"),
        ("WHIRLWIND", "WHIRLWIND SUBSTATION", "KERN", "SCE", "p2", 80, 0, "COMPLETED", np.nan, False, "FULL CAPACITY"),
        ("WHIRLWIND", "WHIRLWIND SUBSTATION", "KERN", "SCE", "p3", 120, 60, "WITHDRAWN", this - 1, True,
         "FULL CAPACITY"),
        ("WHIRLWIND", "WHIRLWIND SUB", "KERN", "SCE", "p4", 300, 0, "WITHDRAWN", 2010, False, "ENERGY ONLY"),
        ("VINCENT", "VINCENT", "LOS ANGELES", "SCE", "p5", 50, 0, "ACTIVE", np.nan, False, "FULL CAPACITY"),
        ("", "", "KERN", "SCE", "footer", np.nan, 0, "ACTIVE", np.nan, False, ""),
    ])
    c15 = project_rows([
        ("WHIRLWIND", "WHIRLWIND", "SAN BERNARDINO", "SCE", "c1", 400, 400, "ACTIVE", np.nan, False,
         "FULL CAPACITY (REQ)"),
        ("WHIRLWIND", "WHIRLWIND", "KERN", "SCE", "c2", 100, 100, "WITHDRAWN", this, False, "ENERGY ONLY (REQ)"),
        ("QUINTO", "QUINTO", "MERCED", "PGAE", "c3", 250, 250, "ACTIVE", np.nan, False, "ENERGY ONLY (REQ)"),
    ])
    out = nodes.build_nodes(pq, c15).set_index("node_key")
    assert "" not in out.index
    assert out.index[0] == "WHIRLWIND"                            # sorted by pipeline_mw desc
    w = out.loc["WHIRLWIND"]
    assert w.poi_base == "WHIRLWIND SUBSTATION" and w.county == "KERN" and w.utility == "SCE"  # mode wins
    assert (w.legacy_active_mw, w.c15_active_mw, w.operating_mw) == (200, 400, 80)
    assert w.pipeline_mw == 600 and w.pipeline_storage_mw == 550
    assert w.wd_alltime_mw == 520                                 # 120 + 300 + 100 (both reports)
    assert w.wd_recent_mw == 220                                  # p3 (last year) + c2 (this year)
    assert w.wd_recent_storage_mw == 160
    assert w.wd_post_phase2_mw == 120
    assert w.c15_withdrawn_mw == 100 and w.c15_fcds_req_mw == 400
    assert w.storage_churn == round(160 / 550, 2)
    assert w.churn_alltime == round(520 / 680, 2)
    assert w.c15_survival == 0.8
    v = out.loc["VINCENT"]
    assert v.c15_active_mw == 0 and v.wd_alltime_mw == 0
    assert pd.isna(v.storage_churn)                               # no storage anywhere -> NaN, not 0
    assert pd.isna(v.c15_survival)
    assert v.churn_alltime == 0.0
    q = out.loc["QUINTO"]
    assert q.legacy_active_mw == 0 and q.c15_active_mw == 250 and q.c15_survival == 1.0
    assert (out.wd_recent_mw <= out.wd_alltime_mw).all()


# ---------------------------------------------------------------- real reports

@pytest.mark.real_data
def test_load_projects_dedupes_nothing_today(real_projects):
    pq, c15 = real_projects
    assert not c15.queue_position.isin(set(pq.queue_position.dropna())).any()
    assert len(c15) > 100


@pytest.mark.real_data
def test_build_nodes_real_whirlwind_joins_both_reports(real_nodes):
    w = real_nodes.set_index("node_key").loc["WHIRLWIND"]
    assert w.legacy_active_mw > 0 and w.c15_active_mw > 0
    assert w.operating_mw > 0
    assert w.pipeline_mw == pytest.approx(w.legacy_active_mw + w.c15_active_mw)
    assert w.county == "KERN" and w.utility == "SCE"


@pytest.mark.real_data
def test_build_nodes_real_invariants(real_nodes):
    n = real_nodes
    assert (n.node_key != "").all() and n.node_key.is_unique
    assert (n.wd_recent_mw <= n.wd_alltime_mw + 1e-6).all()
    # (no wd_recent_storage_mw <= wd_recent_mw check: storage_mw is component MW and legitimately
    # exceeds net-to-grid MW for hybrids)
    assert (n.c15_withdrawn_mw <= n.wd_alltime_mw + 1e-6).all()
    zero_denominator = (n.pipeline_storage_mw + n.operating_storage_mw) == 0
    assert (n.storage_churn.isna() == zero_denominator).all()
    assert n.storage_churn.dropna().ge(0).all()
    assert n.c15_survival.dropna().between(0, 1).all()
    assert n.pipeline_mw.is_monotonic_decreasing
    assert len(n) > 500


@pytest.mark.real_data
def test_join_tpd_real_invariants(real_nodes, real_projects):
    for f in ("tpd_2024.xlsx", "tpd_2025.xlsx"):
        if not (nodes.DATA / f).exists():
            pytest.skip(f"real data file missing: {f}")
    pq, _ = real_projects
    n = nodes.join_tpd(real_nodes.copy(), pq)
    assert len(n) == len(real_nodes)
    for c in nodes.TPD_COLS:
        assert c in n.columns, c
        assert n[c].notna().all() and (n[c] >= 0).all(), c
    assert (n.tpd25_alloc_mw <= n.tpd25_req_mw + 1e-6).all()
    assert (n.tpd25_denied_mw <= n.tpd25_req_mw + 1e-6).all()
    assert (n.tpd25_projects > 0).sum() > 50
    assert n.tpd25_req_mw.sum() > 0 and n.tpd24_fcdsa_projects.sum() > 0


@pytest.mark.real_data
def test_join_wdat_real_invariants(real_nodes):
    if not (nodes.DATA / "wdat_pge.xlsx").exists():
        pytest.skip("real data file missing: wdat_pge.xlsx")
    n = nodes.join_wdat(real_nodes.copy())
    assert len(n) == len(real_nodes)
    for c in nodes.WDAT_COLS:
        assert c in n.columns, c
        assert n[c].notna().all() and (n[c] >= 0).all(), c
    assert (n.wdat_active_projects > 0).sum() > 50
    assert (n.wdat_active_storage_mw <= n.wdat_active_mw + 1e-6).all()
    assert n.loc[n.wdat_active_projects == 0, "wdat_active_mw"].eq(0).all()
