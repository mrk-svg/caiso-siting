"""Pure-geometry helpers in layers.py (the network functions are exercised from a real terminal)."""
import pandas as pd
import pytest

from caiso_siting import layers, nodes


def test_haversine_known_distance():
    # Bakersfield -> Fresno ~ 175 km
    assert 165 < layers.haversine_km(35.3733, -119.0187, 36.7378, -119.7871) < 185


def test_polyline_midpoint_single_segment():
    lat, lon = layers.polyline_midpoint([[[-120.0, 36.0], [-120.0, 37.0]]])
    assert abs(lat - 36.5) < 1e-6 and abs(lon + 120.0) < 1e-6


def test_polyline_midpoint_length_weighted():
    # first segment 1 deg, second 3 deg: midpoint is 2 deg along, i.e. 1 deg into the second segment
    lat, lon = layers.polyline_midpoint([[[-120.0, 36.0], [-120.0, 37.0], [-120.0, 40.0]]])
    assert abs(lat - 38.0) < 0.01


def test_polyline_midpoint_multiple_paths():
    lat, lon = layers.polyline_midpoint([[[-120.0, 36.0], [-120.0, 37.0]], [[-120.0, 37.0], [-120.0, 38.0]]])
    assert abs(lat - 37.0) < 0.01


def test_nearest_vertex():
    lat, lon, km = layers.nearest_vertex([[[-120.0, 36.0], [-119.0, 36.0], [-118.0, 36.0]]], 36.1, -119.05)
    assert (lat, lon) == (36.0, -119.0) and km < 15


def test_point_in_ring_square_and_hole():
    ring = [[-120, 36], [-119, 36], [-119, 37], [-120, 37], [-120, 36]]
    assert layers.point_in_ring(36.5, -119.5, ring)
    assert not layers.point_in_ring(37.5, -119.5, ring)
    feats = [{"geometry": {"rings": [ring]}}]
    assert layers.in_any(36.5, -119.5, feats) and not layers.in_any(35.0, -119.5, feats)


def test_envelope_dimensions():
    e = layers.envelope(36.0, -120.0, 11.1)
    assert e["_type"] == "esriGeometryEnvelope"
    assert abs((e["ymax"] - e["ymin"]) - 0.2) < 0.01
    assert (e["xmax"] - e["xmin"]) > 0.2  # longitude degrees are shorter at 36 N


def test_sql_escape():
    assert layers.sql_escape("O'NEILL") == "O''NEILL"


def test_apply_line_cache_only_replaces_weak_positions(tmp_path, monkeypatch):
    monkeypatch.setattr(nodes, "DATA", tmp_path)
    pd.DataFrame([
        dict(node_key="A B", lat=36.0, lon=-120.0, tline_name="A-B", kv="230"),
        dict(node_key="EXACT", lat=1.0, lon=1.0, tline_name="x", kv="230"),
    ]).to_csv(tmp_path / "poi_lines.csv", index=False)
    df = pd.DataFrame([
        dict(node_key="A B", lat=35.0, lon=-121.0, geo_method="line-one-end", geo_score=0.7, osm_name="A"),
        dict(node_key="EXACT", lat=34.0, lon=-118.0, geo_method="exact", geo_score=1.0, osm_name="Exact Sub"),
        dict(node_key="NOPE", lat=None, lon=None, geo_method="none", geo_score=0.0, osm_name=None),
    ])
    out = nodes.apply_line_cache(df)
    a = out[out.node_key == "A B"].iloc[0]
    assert a.geo_method == "cec-line" and a.lat == 36.0 and a.geo_score == 0.9 and "A-B" in a.osm_name
    assert out[out.node_key == "EXACT"].iloc[0].geo_method == "exact"     # exact stands
    assert out[out.node_key == "NOPE"].iloc[0].geo_method == "none"       # not in cache


def test_apply_line_cache_without_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(nodes, "DATA", tmp_path)
    df = pd.DataFrame([dict(node_key="A", lat=None, lon=None, geo_method="none", geo_score=0.0, osm_name=None)])
    assert nodes.apply_line_cache(df).geo_method.iloc[0] == "none"


@pytest.mark.parametrize("poi,ends", [("MIDWAY- GATES 230 KV LINE", ["MIDWAY", "GATES"]),
                                      ("QUINTO SW STA- FINK SW STA 230 kV", ["QUINTO", "FINK"])])
def test_one_sided_hyphen_endpoints(poi, ends):
    from caiso_siting.common import poi_endpoints
    assert poi_endpoints(poi) == ends
