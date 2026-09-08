"""common.py: the string normalizers every parser shares."""
from __future__ import annotations

import pandas as pd
import pytest

from caiso_siting.common import clean_county, norm_poi, poi_base, poi_endpoints

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


# ------------------------------------------------- known defects (strict xfail: flip when fixed)

def test_norm_poi_strips_hash_numbering_like_no_numbering():
    assert norm_poi("LUGO-PISGAH NO. 2 230 KV LINE") == "LUGO PISGAH"       # works today
    assert norm_poi("TAFT-CUYAMA #1 70KV LINE") == "TAFT CUYAMA"            # fails today: 'TAFT CUYAMA 1'


def test_poi_endpoints_splits_one_sided_hyphen_spacing():
    assert poi_endpoints("MIDWAY- GATES 230 KV LINE") == ["MIDWAY", "GATES"]
    assert poi_endpoints("QUINTO SW STA- FINK SW STA 230 kV") == ["QUINTO", "FINK"]
