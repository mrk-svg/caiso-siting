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
from caiso_siting.config import RECENT_YEARS

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


# --------------------------------------------------- state-aware picking

# Two OSM features share the name "Valley": a CA substation in Riverside and the NV switchyard
# CAISO's C15 rows file under Nye NV. They are ~350 km apart.
VALLEY_ROWS = [
    ("Valley Substation", 33.79, -117.20, 500.0),     # Riverside CA, higher kV
    ("Valley Switch", 36.80, -116.30, 230.0),         # Nye NV
]
AMBIGUOUS_ROWS = [
    ("Valley", 33.79, -117.20, 500.0),
    ("Valley", 36.80, -116.30, 230.0),                # same key, > AMBIGUOUS_KM apart
]
CLOSE_ROWS = [
    ("Gates", 36.00, -120.10, 500.0),
    ("Gates", 36.02, -120.12, 230.0),                 # same key, ~3 km apart: not ambiguous
]


def geocoder(rows, tmp_path, name="none.csv") -> nodes.Geocoder:
    return nodes.Geocoder(osm_frame(rows), tmp_path / name)


def test_pick_prefers_a_candidate_inside_the_filed_state(tmp_path):
    g = geocoder([("Valley", 33.79, -117.20, 500.0), ("Valley", 36.80, -116.30, 230.0)], tmp_path)
    ca = g.match("VALLEY", "CA")[0]
    nv = g.match("VALLEY", "NV")[0]
    assert (ca.lat, ca.lon) == (33.79, -117.20)
    assert (nv.lat, nv.lon) == (36.80, -116.30)       # the 230 kV NV feature beats the 500 kV CA one
    # with no state the highest-kV candidate still wins
    assert g.match("VALLEY")[0].kv == 500.0


def test_pick_falls_back_to_highest_kv_when_no_candidate_is_in_state(tmp_path):
    g = geocoder(VALLEY_ROWS, tmp_path)
    r = g.match("VALLEY SUBSTATION", "OR")[0]         # nothing in Oregon
    assert (r.lat, r.kv) == (33.79, 500.0)


def test_pick_flags_ambiguous_when_candidates_are_far_apart(tmp_path):
    g = geocoder(AMBIGUOUS_ROWS, tmp_path)
    assert g.match("VALLEY")[0]["_ambiguous"] is True
    # once the state narrows it to one candidate the ambiguity is gone
    assert g.match("VALLEY", "NV")[0]["_ambiguous"] is False


def test_pick_is_not_ambiguous_for_nearby_duplicates(tmp_path):
    g = geocoder(CLOSE_ROWS, tmp_path)
    r = g.match("GATES")[0]
    assert r["_ambiguous"] is False and r.kv == 500.0
    assert nodes.AMBIGUOUS_KM == 50


def test_geocode_poi_reports_ambiguous_method_and_half_score(tmp_path):
    g = geocoder(AMBIGUOUS_ROWS, tmp_path)
    r = g.geocode_poi("VALLEY 230 kV")
    assert r["method"] == "ambiguous" and r["score"] == 0.5
    assert (r["lat"], r["lon"]) == (33.79, -117.20)
    # the state resolves it: one candidate left, exact again
    nv = g.geocode_poi("VALLEY 230 kV", "NV")
    assert nv["method"] == "exact" and nv["score"] == 1.0 and nv["lat"] == 36.80


def test_geocode_poi_rejects_an_out_of_state_position(tmp_path):
    g = geocoder([("Valley Switch", 33.79, -117.20, 230.0)], tmp_path)   # only a CA feature exists
    ok = g.geocode_poi("VALLEY SWITCH 230 kV", "CA")
    assert ok["method"] == "exact" and ok["lat"] == 33.79
    bad = g.geocode_poi("VALLEY SWITCH 230 kV", "NV")                    # CAISO filed it in Nye NV
    assert bad["method"] == "state-mismatch"
    assert bad["lat"] is None and bad["lon"] is None and bad["score"] == 0.0
    assert "not in NV" in bad["osm_name"] and "Valley Switch" in bad["osm_name"]
    assert "state-mismatch" in nodes.APPROX_METHODS


def test_geocode_poi_keeps_a_position_when_the_state_is_unknown(tmp_path):
    g = geocoder([("Valley Switch", 33.79, -117.20, 230.0)], tmp_path)
    for st in (None, "", "TX"):
        assert g.geocode_poi("VALLEY SWITCH", st)["method"] == "exact"


def test_geocode_poi_never_rejects_a_hand_override(tmp_path):
    """An override is hand-verified against a source; a bounding box does not get to veto it."""
    ov = write_overrides(tmp_path / "ov.csv", [("TROUT CANYON", 33.79, -117.20, "no", "CAISO notice")])
    g = nodes.Geocoder(osm_frame(VALLEY_ROWS), overrides_path=ov)
    r = g.geocode_poi("TROUT CANYON 230 kV", "NV")     # coordinates are in CA, filed NV
    assert r["method"] == "override" and r["lat"] == 33.79 and r["score"] == 1.0


def test_geocode_poi_rejects_an_out_of_state_approximate_override(tmp_path):
    ov = write_overrides(tmp_path / "ov.csv", [("TROUT CANYON", 33.79, -117.20, "yes", "plant centroid")])
    g = nodes.Geocoder(osm_frame(VALLEY_ROWS), overrides_path=ov)
    assert g.geocode_poi("TROUT CANYON", "NV")["method"] == "state-mismatch"   # only 'override' is exempt
    assert g.geocode_poi("TROUT CANYON", "CA")["method"] == "override-approx"


def test_geocode_poi_rejects_an_out_of_state_line_midpoint(tmp_path):
    g = geocoder([("North Gila", 32.70, -114.50, 500.0), ("Hoodoo Wash", 32.90, -114.10, 500.0)], tmp_path)
    assert g.geocode_poi("NORTH GILA - HOODOO WASH 500 kV", "AZ")["method"] == "line-midpoint"
    assert g.geocode_poi("NORTH GILA - HOODOO WASH 500 kV", "OR")["method"] == "state-mismatch"


def test_unresolvable_poi_reports_none_with_best_score(gc):
    r = gc.geocode_poi("ZZYZX ROAD 115 kV")
    assert r["method"] == "none" and r["lat"] is None and r["lon"] is None
    assert 0.0 <= r["score"] < 0.85


# ------------------------------------------------------ county_centroid_fallback

def node_frame(rows) -> pd.DataFrame:
    """Columns county_centroid_fallback reads. `state` keys the centroid together with the county."""
    return pd.DataFrame(rows, columns=["node_key", "state", "county", "lat", "lon", "geo_method",
                                       "geo_score", "osm_name", "pipeline_mw"])


def test_county_centroid_fallback(capsys):
    n = node_frame([
        ("A", "CA", "KERN", 35.0, -118.0, "exact", 1.0, "a", 100),
        ("B", "CA", "KERN", 36.0, -119.0, "fuzzy", 0.9, "b", 100),
        ("C", "CA", "KERN/LOS ANGELES", 37.0, -120.0, "exact", 1.0, "c", 100),  # KERN (first county)
        ("D", "CA", "KERN/KINGS", np.nan, np.nan, "none", 0.0, None, 500),      # -> CA KERN centroid
        ("E", "CA", "KINGS", 36.1, -119.9, "exact", 1.0, "e", 10),
        ("F", "CA", "KINGS", 36.2, -119.8, "exact", 1.0, "f", 10),
        ("G", "CA", "KINGS", np.nan, np.nan, "none", 0.0, None, 50),            # only 2 located -> stays NaN
        ("H", "CA", "", np.nan, np.nan, "none", 0.0, None, 5),
    ])
    out = nodes.county_centroid_fallback(n)
    d = out.set_index("node_key").loc["D"]
    assert d.geo_method == "county-centroid" and d.geo_score == 0.3
    assert (d.lat, d.lon) == (36.0, -119.0)                       # median of the three KERN nodes
    assert d.osm_name == "median of located nodes in CA KERN"
    g = out.set_index("node_key").loc["G"]
    assert pd.isna(g.lat) and g.geo_method == "none"
    assert pd.isna(out.set_index("node_key").loc["H", "lat"])
    # located nodes untouched
    assert out.set_index("node_key").loc["A", "geo_method"] == "exact"
    assert "1 nodes placed at county centroids (500 MW)" in capsys.readouterr().out


def test_county_centroid_keys_on_state_and_county():
    """Two same-named counties in different states must not pool: CA and NV both have a 'LINCOLN'
    here, and the NV node must never be dragged to the CA median."""
    n = node_frame([
        ("CA1", "CA", "LINCOLN", 38.0, -121.0, "exact", 1.0, "a", 1),
        ("CA2", "CA", "LINCOLN", 38.2, -121.2, "exact", 1.0, "b", 1),
        ("CA3", "CA", "LINCOLN", 38.4, -121.4, "exact", 1.0, "c", 1),
        ("CA4", "CA", "LINCOLN", np.nan, np.nan, "none", 0.0, None, 1),
        ("NV1", "NV", "LINCOLN", 37.5, -114.5, "exact", 1.0, "d", 1),
        ("NV2", "NV", "LINCOLN", 37.7, -114.7, "exact", 1.0, "e", 1),
        ("NV3", "NV", "LINCOLN", np.nan, np.nan, "none", 0.0, None, 1),   # only 2 NV sources -> unplaced
    ])
    out = nodes.county_centroid_fallback(n).set_index("node_key")
    assert (out.loc["CA4", "lat"], out.loc["CA4", "lon"]) == (38.2, -121.2)
    assert out.loc["CA4", "osm_name"] == "median of located nodes in CA LINCOLN"
    assert pd.isna(out.loc["NV3", "lat"])          # would have been placed in CA if county alone keyed it


def test_county_centroid_ignores_out_of_state_sources():
    """A source node whose own position is outside its filed state cannot drag the county median."""
    n = node_frame([
        ("A", "NV", "NYE", 36.0, -116.0, "exact", 1.0, "a", 1),
        ("B", "NV", "NYE", 37.0, -117.0, "exact", 1.0, "b", 1),
        ("C", "NV", "NYE", 33.9, -117.5, "exact", 1.0, "wrong state", 1),   # in CA, filed NV
        ("D", "NV", "NYE", np.nan, np.nan, "none", 0.0, None, 1),
    ])
    out = nodes.county_centroid_fallback(n).set_index("node_key")
    assert pd.isna(out.loc["D", "lat"])            # only 2 usable sources once C is rejected
    assert out.loc["C", "lat"] == 33.9             # the bad source itself is left alone here


def test_county_centroid_ignores_prior_centroids_as_sources():
    n = node_frame([
        ("A", "CA", "KERN", 35.0, -118.0, "county-centroid", 0.3, "x", 1),
        ("B", "CA", "KERN", 35.0, -118.0, "county-centroid", 0.3, "x", 1),
        ("C", "CA", "KERN", 35.0, -118.0, "county-centroid", 0.3, "x", 1),
        ("D", "CA", "KERN", np.nan, np.nan, "none", 0.0, None, 1),
        ("E", "CA", "FRESNO", 36.7, -119.8, "exact", 1.0, "e", 1),   # keeps `loc` non-empty (see below)
    ])
    out = nodes.county_centroid_fallback(n)
    assert pd.isna(out.set_index("node_key").loc["D", "lat"])


def test_county_centroid_with_no_located_nodes_is_a_noop():
    n = node_frame([
        ("A", "CA", "KERN", np.nan, np.nan, "none", 0.0, None, 1),
        ("B", "CA", "KERN", np.nan, np.nan, "none", 0.0, None, 1),
    ])
    out = nodes.county_centroid_fallback(n)
    assert out.lat.isna().all() and out.geo_method.tolist() == ["none", "none"]


def test_geocode_nodes_survives_a_missing_osm_file(monkeypatch, tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    data.mkdir()
    out.mkdir()
    monkeypatch.setattr(nodes, "DATA", data)
    monkeypatch.setattr(nodes, "OUT", out)
    monkeypatch.setattr(nodes.Geocoder.__init__, "__defaults__", (data / "poi_overrides.csv",))
    n = pd.DataFrame({"node_key": ["A"], "poi_base": ["A"], "county": ["KERN"], "state": ["CA"],
                      "pipeline_mw": [1.0]})
    assert nodes.geocode_nodes(n).geo_method.tolist() == ["none"]


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
        "state": ["CA", "CA", "AZ", "CA"],
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


def test_build_nodes_phase2_attrition_commitment_and_counts():
    """Phase II attrition = of MW that received Phase II results, the share that withdrew; commitment = ACTIVE MW
    with an executed IA; every ratio carries the project count behind it."""
    this = nodes.THIS_YEAR
    pq = project_rows([
        ("GATES", "GATES", "FRESNO", "PGAE", "a", 500, 500, "ACTIVE", np.nan, False, "FULL CAPACITY"),
        ("GATES", "GATES", "FRESNO", "PGAE", "b", 300, 0, "ACTIVE", np.nan, False, "FULL CAPACITY"),
        ("GATES", "GATES", "FRESNO", "PGAE", "c", 200, 0, "COMPLETED", np.nan, False, "FULL CAPACITY"),
        ("GATES", "GATES", "FRESNO", "PGAE", "d", 1000, 1000, "WITHDRAWN", this - 1, True, "FULL CAPACITY"),
        ("GATES", "GATES", "FRESNO", "PGAE", "e", 400, 0, "WITHDRAWN", 2012, False, "FULL CAPACITY"),
        ("VIEJO", "VIEJO", "ORANGE", "SCE", "t", 300, 300, "ACTIVE", np.nan, False, "FULL CAPACITY"),
    ])
    pq["study_fas_phase2"] = ["COMPLETE", "", "COMPLETE", "COMPLETE", "", "COMPLETE"]
    pq["ia_status"] = ["EXECUTED", "IN PROGRESS", "EXECUTED", "", "", "EXECUTED"]
    c15 = project_rows([
        ("VIEJO", "VIEJO", "ORANGE", "SCE", "k", 1000, 1000, "WITHDRAWN", this, False, "FULL CAPACITY (REQ)"),
    ])
    out = nodes.build_nodes(pq, c15).set_index("node_key")
    g = out.loc["GATES"]
    assert g.p2_reached_projects == 3 and g.p2_reached_mw == 1700        # a, c, d received Phase II results
    assert g.p2_withdrawn_projects == 1 and g.p2_withdrawn_mw == 1000 == g.wd_post_phase2_mw
    assert g.p2_attrition == round(1000 / 1700, 2)
    assert g.committed_projects == 1 and g.committed_mw == 500           # ACTIVE + EXECUTED only (not c, not b)
    assert g.churn_n == 1 + 2 + 0 + 1 and g.c15_n == 0 and g.p2_n == 3    # wd_recent(d) + active(a,b) + operating(c)
    v = out.loc["VIEJO"]
    assert v.storage_churn == round(1000 / 300, 2) and v.churn_n == 2     # right ratio; the n says not to trust it
    assert v.c15_survival == 0.0 and v.c15_n == 1
    assert v.p2_reached_mw == 300 and v.p2_withdrawn_mw == 0 and v.p2_attrition == 0.0 and v.p2_n == 1
    assert out.p2_attrition.dropna().between(0, 1).all()


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
    assert n.p2_attrition.dropna().between(0, 1).all()
    assert (n.p2_withdrawn_mw <= n.p2_reached_mw + 1e-6).all()
    assert (n.p2_withdrawn_mw == n.wd_post_phase2_mw).all()
    assert (n.committed_mw <= n.legacy_active_mw + 1e-6).all()
    assert (n.churn_n >= 0).all() and (n.c15_n >= 0).all()
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


# --------------------------------------------- real-data geography invariants

@pytest.mark.real_data
def test_published_nodes_have_no_out_of_state_position():
    """Every position in outputs/nodes.csv must survive the wrong-state check. A node placed in the
    wrong state is a map that lies; geocode_poi is supposed to demote those to `state-mismatch`."""
    path = nodes.OUT / "nodes.csv"
    if not path.exists():
        pytest.skip("outputs/nodes.csv not built (run `caiso-siting nodes`)")
    n = pd.read_csv(path)
    assert {"lat", "lon", "state", "geo_method"} <= set(n.columns)
    bad = n[[nodes.in_state(r.lat, r.lon, r.state) is False for r in n.itertuples()]]
    assert bad.empty, (
        f"{len(bad)} published nodes sit outside the state they were filed under:\n"
        + bad[["node_key", "state", "county", "lat", "lon", "geo_method", "osm_name"]].head(15).to_string())
    # a node the geocoder rejected carries no position at all
    rejected = n[n.geo_method == "state-mismatch"]
    assert rejected.lat.isna().all() and rejected.lon.isna().all()


@pytest.mark.real_data
def test_recent_window_is_five_years_inclusive():
    assert nodes.RECENT_FROM_YEAR == nodes.THIS_YEAR - RECENT_YEARS + 1
    assert nodes.THIS_YEAR - nodes.RECENT_FROM_YEAR + 1 == RECENT_YEARS   # 5 calendar years, not 6


@pytest.mark.real_data
def test_recent_storage_never_exceeds_recent_mw_except_on_zero_net_filings(real_nodes, real_projects):
    """storage_mw is capped at net_mw, so the storage share of a node's recent withdrawals cannot
    exceed the withdrawals themselves — except where the underlying filing carries net_mw <= 0 and
    the component nameplate is all there is."""
    n = real_nodes
    over = n[n.wd_recent_storage_mw > n.wd_recent_mw + 1e-6]
    pq, c15 = real_projects
    both = pd.concat([pq, c15], ignore_index=True, sort=False)
    recent_wd = both[(both.sheet_status == "WITHDRAWN")
                     & (both.withdrawn_year.fillna(0) >= nodes.RECENT_FROM_YEAR)]
    for nk in over.node_key:
        rows = recent_wd[recent_wd.node_key == nk]
        assert not rows.empty, nk
        assert (rows.net_mw.fillna(0) <= 0).all(), (
            f"{nk}: storage exceeds withdrawn MW but the filings carry a positive net_mw\n"
            + rows[["project_name", "net_mw", "storage_mw"]].to_string())
    # every node with a positive net_mw behind it obeys the inequality
    ok = n[~n.node_key.isin(over.node_key)]
    assert (ok.wd_recent_storage_mw <= ok.wd_recent_mw + 1e-6).all()
    assert len(over) < 10, "the zero-net_mw exception should stay a handful of filings"


@pytest.mark.real_data
def test_node_storage_never_exceeds_capped_project_storage(real_projects):
    pq, c15 = real_projects
    for df in (pq, c15):
        over = df[df.storage_mw > df.net_mw.fillna(-1) + 1e-6]
        assert (over.net_mw.fillna(0) <= 0).all()
        assert (df.storage_mw <= df.storage_component_mw + 1e-6).all()


def test_map_escapes_hostile_source_text(tmp_path, monkeypatch):
    """A POI name containing markup must not reach the map DOM unescaped (stored XSS via a CAISO file)."""
    monkeypatch.setattr(nodes, "OUT", tmp_path)
    evil = 'EVIL<img src=x onerror=alert(1)>'
    df = pd.DataFrame([dict(
        node_key="EVIL", poi_base=evil, county="KERN", utility="SCE", state="CA", lat=35.0, lon=-119.0,
        legacy_active_mw=100.0, c15_active_mw=0.0, operating_mw=0.0, pipeline_mw=100.0,
        wd_recent_mw=0.0, wd_recent_storage_mw=0.0, wd_alltime_mw=0.0, wd_post_phase2_mw=0.0,
        storage_churn=float("nan"), c15_survival=float("nan"), c16_poi_status="", c16_poi_note="",
        geo_score=1.0, geo_method="exact", osm_name="</script><script>alert(2)</script>",
    )])
    nodes.write_map(df)
    html = (tmp_path / "nodes_map.html").read_text()
    assert "</script><script>alert(2)" not in html          # JSON payload cannot close the script block
    # every "<" in the embedded JSON is \u003c now, so no source string can open OR close a tag
    assert "\\u003cscript>" in html or "\\u003c/script>" in html
    assert "esc(p.poi)" in html and "esc(p.osm)" in html      # popup fields go through the escaper
    assert 'integrity="sha256-' in html                         # Leaflet loads with SRI


# --- domain review 2026-09-16: ambiguity must not be resolved by guessing ---------------------

def test_sole_mode_returns_blank_on_a_tie():
    """A 2-2 split on utility published PGAE for Los Angeles County substations, because
    pandas.mode() breaks ties alphabetically. A tie means unknown, not the first letter."""
    assert nodes.sole_mode(pd.Series(["SCE", "SCE", "PGAE", "PGAE"])) == ""
    assert nodes.sole_mode(pd.Series(["SCE", "SCE", "PGAE"])) == "SCE"
    assert nodes.sole_mode(pd.Series(["", "", "SCE"])) == "SCE"
    assert nodes.sole_mode(pd.Series(["", ""])) == ""
    assert nodes.sole_mode(pd.Series([float("nan"), "SCE", "SCE"])) == "SCE"


def test_quarantine_drops_proven_wrong_positions(tmp_path, monkeypatch):
    """A confidently wrong coordinate is worse than none: it is mapped and it wins distance
    joins. Quarantined nodes keep no position and are marked disputed."""
    q = tmp_path / "geo_quarantine.csv"
    q.write_text("node_key,reason,source,source_date\nWALNUT,matched the wrong Walnut,review,2026-09-16\n")
    monkeypatch.setattr(nodes, "DATA", tmp_path)
    df = pd.DataFrame({"node_key": ["WALNUT", "GATES"], "lat": [37.49, 36.0], "lon": [-120.9, -120.1],
                       "geo_score": [1.0, 1.0], "osm_name": ["Walnut Substation", "Gates"],
                       "geo_method": ["exact", "exact"]})
    out = nodes.quarantine_positions(df.copy())
    w = out[out.node_key == "WALNUT"].iloc[0]
    assert w.geo_method == "disputed"
    assert pd.isna(w.lat) and pd.isna(w.lon) and pd.isna(w.geo_score)
    g = out[out.node_key == "GATES"].iloc[0]
    assert g.geo_method == "exact" and g.lat == 36.0
    assert "disputed" in nodes.APPROX_METHODS
    assert "disputed" not in __import__("caiso_siting.eia860", fromlist=["x"]).REAL_POSITIONS
