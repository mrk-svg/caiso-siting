"""common.py: the string normalizers every parser shares."""
from __future__ import annotations

import pandas as pd
import pytest

from caiso_siting.common import (
    NON_STORAGE_FUELS,
    STATE_BBOX,
    cap_storage_mw,
    clean_county,
    haversine_km,
    in_state,
    norm_poi,
    poi_base,
    poi_endpoints,
    tech_flags,
)

# ------------------------------------------------------------------ clean_county

@pytest.mark.parametrize("raw, expected", [
    ("KERN COUNTY", "KERN"),                     # " COUNTY" suffix stripped
    ("L.A", "LOS ANGELES"),                      # hand-typed abbreviation (public report)
    ("L.A.", "LOS ANGELES"),
    ("LA", "LOS ANGELES"),
    ("MERCED / FRESNO", "FRESNO/MERCED"),        # spaced slash -> sorted "A/B"
    ("KINGS AND FRESNO", "FRESNO/KINGS"),        # " AND " -> "/"
    ("Fresno & Merced", "FRESNO/MERCED"),        # "&" -> "/"
    ("SAN BERNADINO", "SAN BERNARDINO"),         # common misspelling
    ("San Bernadino", "SAN BERNARDINO"),
    ("king", "KINGS"),                           # Cluster 15 lower-case singular
    ("MOJAVE", "MOHAVE"),                        # AZ county; Mojave is a town in Kern
    ("SAN LUIS OBISPO COUNTY", "SAN LUIS OBISPO"),
    ("Tijuana, Mexico", "TIJUANA"),
    ("Municipality of Tecate", "TECATE"),
    ("  Los   Angeles ", "LOS ANGELES"),         # whitespace collapse
    ("Kern/Kings", "KERN/KINGS"),                # already canonical multi-county stays
    ("", ""),
])
def test_clean_county_variants(raw, expected):
    assert clean_county(pd.Series([raw])).iloc[0] == expected


def test_clean_county_null_becomes_empty_string():
    out = clean_county(pd.Series([None, float("nan"), "KERN"]))
    assert out.tolist() == ["", "", "KERN"]


def test_clean_county_multi_county_is_sorted_and_fixed_per_part():
    # both orderings collapse to one key; per-part fixes apply inside multi-county strings
    s = pd.Series(["KINGS/KERN", "KERN / KINGS", "KING AND SAN BERNADINO", "LA/KERN"])
    assert clean_county(s).tolist() == ["KERN/KINGS", "KERN/KINGS", "KINGS/SAN BERNARDINO", "KERN/LOS ANGELES"]


def test_clean_county_preserves_index():
    s = pd.Series(["kern", "l.a"], index=[10, 20])
    out = clean_county(s)
    assert list(out.index) == [10, 20]
    assert out.tolist() == ["KERN", "LOS ANGELES"]


# --------------------------------------------------------------------- norm_poi

@pytest.mark.parametrize("variant", [
    "WHIRLWIND SUBSTATION 230 kV", "Whirlwind", "WHIRLWIND SUB", "Whirlwind Sub",
    "WHIRLWIND 230KV", "Whirlwind Substation 230 kV Bus", "whirlwind switching station",
])
def test_norm_poi_equivalent_spellings_share_one_key(variant):
    assert norm_poi(variant) == "WHIRLWIND"


def test_norm_poi_strips_parentheticals():
    assert norm_poi("NORTH GILA - HOODOO WASH (SDGE Portion Only)") == "NORTH GILA HOODOO WASH"
    assert norm_poi("Tesla (fka Contra Costa) 230 kV") == "TESLA"


@pytest.mark.parametrize("raw, expected", [
    ("MOSS LANDING PP 115 kV", "MOSS LANDING"),
    ("Contra Costa Power Plant 230 kV bus", "CONTRA COSTA"),
    ("OTAY MESA SWITCHYARD 230 KV", "OTAY MESA"),
    ("QUINTO SW STA 230 kV", "QUINTO"),
    ("LUGO-PISGAH NO. 2 230 KV TRAN LINE", "LUGO PISGAH TRAN"),   # 'NO. 2', 'LINE', voltage removed
    ("Vaca-Dixon 230 kV", "VACA DIXON"),                          # hyphen -> space, one key
    ("GREENLEAF 115 KV TAP", "GREENLEAF"),
    ("", ""),
])
def test_norm_poi_noise_removal(raw, expected):
    assert norm_poi(raw) == expected


def test_norm_poi_non_string_input():
    assert norm_poi(None) == "NONE"      # str(None); callers fillna("") first
    assert norm_poi(123) == "123"


# ---------------------------------------------------------------- poi_endpoints

@pytest.mark.parametrize("raw, expected", [
    ("NORTH GILA - HOODOO WASH 500 kV", ["NORTH GILA", "HOODOO WASH"]),
    ("DELANEY-COLORADO RIVER", ["DELANEY", "COLORADO RIVER"]),
    ("VACA-DIXON", ["VACA", "DIXON"]),
    ("Metcalf-Manning 500 kV", ["METCALF", "MANNING"]),
    ("MIDWAY TO GATES 230 KV LINE", ["MIDWAY", "GATES"]),
    ("NORTH GILA - HOODOO WASH (SDGE Portion Only)", ["NORTH GILA", "HOODOO WASH"]),
])
def test_poi_endpoints_line_pois(raw, expected):
    assert poi_endpoints(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("WHIRLWIND SUBSTATION 230 kV", ["WHIRLWIND"]),
    ("Whirlwind", ["WHIRLWIND"]),
    ("MOSS LANDING PP 115 kV", ["MOSS LANDING"]),
])
def test_poi_endpoints_single_substation(raw, expected):
    assert poi_endpoints(raw) == expected


def test_poi_endpoints_caps_at_two_and_drops_short_fragments():
    ends = poi_endpoints("ELDORADO-BAKER-COOLWATER-DUNN SIDING 115 KV LINE")
    assert ends == ["ELDORADO", "BAKER"]
    # a fragment shorter than 3 chars ('E' from 'Bus E') never becomes an endpoint
    assert poi_endpoints("Tesla Sub 230kV Bus E") == ["TESLA"]


def test_poi_endpoints_falls_back_to_norm_poi_when_nothing_survives():
    assert poi_endpoints("") == [""]
    assert poi_endpoints("AB") == ["AB"]


# --------------------------------------------------------------------- poi_base

def test_poi_base_strips_voltage_suffix_only():
    s = pd.Series(["NORTH GILA - HOODOO WASH 500 kV", "Whirlwind Substation 230kV Bus", "Vincent", None])
    assert poi_base(s).tolist() == ["NORTH GILA - HOODOO WASH", "WHIRLWIND SUBSTATION", "VINCENT", ""]


def test_norm_poi_strips_hash_numbering_like_no_numbering():
    assert norm_poi("LUGO-PISGAH NO. 2 230 KV LINE") == "LUGO PISGAH"       # works today
    assert norm_poi("TAFT-CUYAMA #1 70KV LINE") == "TAFT CUYAMA"            # fails today: 'TAFT CUYAMA 1'


def test_poi_endpoints_splits_one_sided_hyphen_spacing():
    assert poi_endpoints("MIDWAY- GATES 230 KV LINE") == ["MIDWAY", "GATES"]
    assert poi_endpoints("QUINTO SW STA- FINK SW STA 230 kV") == ["QUINTO", "FINK"]


# ---------------------------------------------------------------- geography

def test_haversine_km_known_distances():
    assert haversine_km(35.0, -118.0, 35.0, -118.0) == 0.0
    # one degree of latitude is ~111 km anywhere
    assert haversine_km(35.0, -118.0, 36.0, -118.0) == pytest.approx(111.2, abs=0.5)
    # LA basin -> Las Vegas, ~365 km
    assert haversine_km(34.05, -118.24, 36.17, -115.14) == pytest.approx(365, abs=10)
    assert haversine_km(35.0, -118.0, 36.0, -119.0) == haversine_km(36.0, -119.0, 35.0, -118.0)


@pytest.mark.parametrize("lat, lon, state, expected", [
    (35.0, -118.5, "CA", True),        # Kern County
    (36.17, -115.14, "NV", True),      # Las Vegas
    (32.70, -114.50, "AZ", True),      # Yuma
    (34.05, -118.24, "NV", False),     # Los Angeles filed as Nevada
    (33.45, -112.07, "CA", False),     # Phoenix filed as California
    (35.0, -118.5, "AZ", False),       # Kern County filed as Arizona
    (44.0, -123.0, "CA", False),       # Oregon filed as California
    (34.05, -118.24, "ca", True),      # case and whitespace tolerant
    (34.05, -118.24, " CA ", True),
])
def test_in_state_inside_and_outside(lat, lon, state, expected):
    assert in_state(lat, lon, state) is expected


@pytest.mark.parametrize("lat, lon, state", [
    (35.0, -118.5, "TX"),              # state with no bounding box
    (35.0, -118.5, ""),
    (35.0, -118.5, None),
    (35.0, -118.5, float("nan")),
    (None, None, "CA"),                # no coordinates
    (float("nan"), -118.5, "CA"),
    (35.0, float("nan"), "CA"),
    (None, -118.5, "CA"),
])
def test_in_state_unknown_returns_none(lat, lon, state):
    assert in_state(lat, lon, state) is None


def test_in_state_boxes_are_deliberately_generous():
    """The boxes are rectangles around each state, so border positions read as inside more than one.
    in_state is a wrong-state alarm, never a placement rule — lock that in so nobody tightens it
    expecting polygon accuracy."""
    assert in_state(32.70, -114.50, "CA") is True and in_state(32.70, -114.50, "AZ") is True
    assert in_state(36.17, -115.14, "CA") is True      # Las Vegas sits inside the CA rectangle


def test_in_state_covers_every_state_in_the_bbox_table():
    assert set(STATE_BBOX) >= {"CA", "NV", "AZ", "OR", "UT", "MX"}
    for st, (lo_lat, hi_lat, lo_lon, hi_lon) in STATE_BBOX.items():
        mid = ((lo_lat + hi_lat) / 2, (lo_lon + hi_lon) / 2)
        assert in_state(*mid, st) is True
        assert in_state(lo_lat - 1, mid[1], st) is False


# ------------------------------------------------------------- tech_flags

def flags(*blobs) -> pd.DataFrame:
    return tech_flags(pd.Series(list(blobs)))


def test_tech_flags_standalone_storage():
    f = flags("STORAGE BATTERY", "Storage", "BATTERY")
    assert f.has_storage.all() and f.is_standalone_storage.all()
    assert not f.has_solar.any() and not f.has_wind.any()


@pytest.mark.parametrize("blob", [
    "SOLAR PV, STORAGE",                    # WDAT's hybrid spelling
    "Photovoltaic Storage",
    "PHOTOVOLTAIC/SOLAR STORAGE/BATTERY",   # Cluster 15 spelling
    "Wind Turbine Storage Battery",
    "STORAGE ENGINE",                       # non-storage fuel alongside the battery
    "Battery Combustion Turbine",
    "STORAGE FUEL CELL",
    "STORAGE COGENERATION",
    "STORAGE STEAM",
    "STORAGE NUCLEAR",
    "STORAGE NATURAL GAS",
    "STORAGE GEOTHERMAL",
])
def test_tech_flags_hybrids_are_not_standalone(blob):
    f = flags(blob)
    assert f.has_storage.iloc[0]
    assert not f.is_standalone_storage.iloc[0], blob


def test_tech_flags_solar_spellings():
    f = flags("Solar PV", "PHOTOVOLTAIC", "SOLAR", "PV", "Supervisory", "PVC PIPE")
    assert f.has_solar.tolist() == [True, True, True, True, False, False]   # \bPV\b, not any 'PV' substring


def test_tech_flags_wind_and_empty():
    f = flags("Wind Turbine", "", None, "Natural Gas")
    assert f.has_wind.tolist() == [True, False, False, False]
    assert not f.has_storage.any() and not f.is_standalone_storage.any()


def test_tech_flags_preserves_index_and_columns():
    s = pd.Series(["STORAGE", "SOLAR"], index=[7, 9])
    f = tech_flags(s)
    assert list(f.columns) == ["has_storage", "has_solar", "has_wind", "is_standalone_storage"]
    assert list(f.index) == [7, 9]
    assert f.dtypes.eq(bool).all()


def test_non_storage_fuels_covers_the_thermal_families():
    for token in ("GAS", "COMBUSTION", "COMBINED", "GEOTHERMAL", "HYDRO", "BIOMASS", "ENGINE",
                  "TURBINE", "FUEL CELL", "COGENERATION", "STEAM", "NUCLEAR"):
        assert token in NON_STORAGE_FUELS


# ---------------------------------------------------------- cap_storage_mw

def test_cap_storage_mw_caps_at_net():
    comp = pd.Series([2807.0, 500.0, 100.0])
    net = pd.Series([1400.0, 500.0, 250.0])
    # RED BLUFF's ETERNAL PUMPED STORAGE lists a 1407 MW pumped plus a 1400 MW battery on a 1400 MW POI
    assert cap_storage_mw(comp, net).tolist() == [1400.0, 500.0, 100.0]


def test_cap_storage_mw_keeps_component_when_net_is_zero_or_missing():
    comp = pd.Series([300.0, 300.0, 300.0, 0.0])
    net = pd.Series([0.0, float("nan"), -5.0, float("nan")])
    assert cap_storage_mw(comp, net).tolist() == [300.0, 300.0, 300.0, 0.0]


def test_cap_storage_mw_accepts_string_net_and_preserves_index():
    comp = pd.Series([300.0, 300.0], index=[3, 4])
    out = cap_storage_mw(comp, pd.Series(["250", "junk"], index=[3, 4]))
    assert out.tolist() == [250.0, 300.0]      # unparseable net is treated as missing
    assert list(out.index) == [3, 4]


def test_cap_storage_mw_zero_storage_stays_zero():
    assert cap_storage_mw(pd.Series([0.0, 0.0]), pd.Series([100.0, float("nan")])).tolist() == [0.0, 0.0]
