"""Shared normalizers used by every parser. Keep all string-cleaning rules here so
the two CAISO reports and any future utility report agree on keys."""
from __future__ import annotations

import math
import re

import pandas as pd

# --- county -----------------------------------------------------------------
# Both CAISO reports hand-type county names. Multi-county projects are kept as
# "A/B" (sorted) so they group consistently; do not pick one arbitrarily.
_COUNTY_FIX = {
    "SAN BERNADINO": "SAN BERNARDINO",
    "KING": "KINGS",
    "L.A": "LOS ANGELES", "L.A.": "LOS ANGELES", "LA": "LOS ANGELES",
    "CHURCH": "CHURCHILL",
    "MOJAVE": "MOHAVE",           # AZ county is Mohave; "Mojave" is a town in Kern
    "SAN LUIS OBISPO COUNTY": "SAN LUIS OBISPO",
    "TIJUANA, MEXICO": "TIJUANA",
    "MUNICIPALITY OF TECATE": "TECATE",
}


def clean_county(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.upper().str.strip()
    s = s.str.replace(r"\s+COUNTY\b", "", regex=True)
    s = s.str.replace(r"\s*(?:/|&|\bAND\b)\s*", "/", regex=True)   # "KINGS AND FRESNO" -> "KINGS/FRESNO"
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    s = s.map(lambda v: "/".join(sorted(_COUNTY_FIX.get(p.strip(), p.strip()) for p in v.split("/"))) if v else v)
    return s


# --- point of interconnection ----------------------------------------------
_RAD = math.pi / 180

_NOISE = re.compile(
    r"\b(SUBSTATION|SUB|SW STA|SWITCHING STATION|SWITCHING STA|SWITCHYARD|SWITCH|SW|STA|STATION|"
    r"PP|POWER PLANT|GENERATING STATION|GEN STA|BUS|TAP|LINE|SEGMENT|JUNCTION|JCT|"
    r"NO\.?\s*\d+|#\s*\d+|\d{2,3}\s*KV|\d{2,3}KV)\b"
)


def norm_poi(name) -> str:
    """Canonical node key: 'WHIRLWIND SUBSTATION 230 kV' == 'WHIRLWIND' == 'Whirlwind Sub'."""
    s = str(name).upper()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"#\s*\d+", " ", s)          # '#1' circuits: no word boundary before '#', so handle before _NOISE
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def poi_endpoints(poi) -> list[str]:
    """'NORTH GILA - HOODOO WASH 500 kV' -> ['NORTH GILA', 'HOODOO WASH'] (max 2)."""
    base = re.sub(r"\(.*?\)", " ", str(poi).upper())
    base = re.sub(r"\d{2,3}\s*KV.*$", "", base)
    parts = [norm_poi(p) for p in re.split(r"\s*-\s+|\s+-\s*|-(?=[A-Z])|\s+TO\s+", base) if p.strip()]
    parts = [p for p in parts if len(p) >= 3]
    return parts[:2] if parts else [norm_poi(poi)]


def poi_base(s: pd.Series) -> pd.Series:
    """Display label: strip the voltage suffix only."""
    return s.fillna("").str.upper().str.replace(r"\s*\d{2,3}\s*KV.*$", "", regex=True).str.strip()


# --- geography --------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    a = 0.5 - math.cos((lat2 - lat1) * _RAD) / 2 + math.cos(lat1 * _RAD) * math.cos(lat2 * _RAD) * \
        (1 - math.cos((lon2 - lon1) * _RAD)) / 2
    return 12742 * math.asin(math.sqrt(a))


# Generous bounding boxes (lat_min, lat_max, lon_min, lon_max) for the states that appear in the
# CAISO reports. Used only to catch a geocode that lands in the wrong state — never to place a node.
STATE_BBOX = {
    "CA": (32.45, 42.05, -124.50, -114.10),
    "NV": (34.95, 42.05, -120.05, -113.95),
    "AZ": (31.30, 37.05, -114.85, -109.00),
    "OR": (41.95, 46.30, -124.60, -116.45),
    "UT": (36.95, 42.05, -114.10, -109.00),
    "MX": (28.00, 32.80, -118.50, -112.50),
}


def in_state(lat, lon, state) -> bool | None:
    """True / False / None (state unknown or coordinates missing). A False here means the position
    is provably not in the state the developer filed."""
    box = STATE_BBOX.get(str(state).strip().upper())
    if box is None or lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return None
    lo_lat, hi_lat, lo_lon, hi_lon = box
    return bool(lo_lat <= lat <= hi_lat and lo_lon <= lon <= hi_lon)


# --- technology flags -------------------------------------------------------

NON_STORAGE_FUELS = ("GAS|COMBUSTION|COMBINED|GEOTHERMAL|HYDRO|BIOMASS|ENGINE|TURBINE|"
                     "FUEL CELL|COGENERATION|STEAM|NUCLEAR")


def tech_flags(blob: pd.Series) -> pd.DataFrame:
    """One definition of has_storage / has_solar / has_wind / is_standalone_storage for every report.
    `blob` is the concatenated type + fuel text for a row, upper-cased."""
    blob = blob.fillna("").str.upper()
    out = pd.DataFrame(index=blob.index)
    out["has_storage"] = blob.str.contains("STORAGE|BATTERY")
    out["has_solar"] = blob.str.contains("SOLAR|PHOTOVOLTAIC|\\bPV\\b")
    out["has_wind"] = blob.str.contains("WIND")
    out["is_standalone_storage"] = out.has_storage & ~out.has_solar & ~out.has_wind & \
        ~blob.str.contains(NON_STORAGE_FUELS)
    return out


def cap_storage_mw(component_mw: pd.Series, net_mw: pd.Series) -> pd.Series:
    """Storage MW at the point of interconnection.

    The component columns (MW-1..3) are nameplate per component and can exceed the project's
    net-to-grid figure — a few filings even list two storage components (a pumped-storage and a
    battery line) which would otherwise double the node's storage total. Cap at net_mw; where
    net_mw is missing or zero (a handful of filings), keep the component sum and say so."""
    net = pd.to_numeric(net_mw, errors="coerce")
    return component_mw.where(net.isna() | (net <= 0), component_mw.clip(upper=net))
