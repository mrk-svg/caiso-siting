"""Shared normalizers used by every parser. Keep all string-cleaning rules here so
the two CAISO reports and any future utility report agree on keys."""
from __future__ import annotations

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
_NOISE = re.compile(
    r"\b(SUBSTATION|SUB|SW STA|SWITCHING STATION|SWITCHING STA|SWITCHYARD|SWITCH|SW|STA|STATION|"
    r"PP|POWER PLANT|GENERATING STATION|GEN STA|BUS|TAP|LINE|SEGMENT|JUNCTION|JCT|"
    r"NO\.?\s*\d+|#\s*\d+|\d{2,3}\s*KV|\d{2,3}KV)\b"
)


def norm_poi(name) -> str:
    """Canonical node key: 'WHIRLWIND SUBSTATION 230 kV' == 'WHIRLWIND' == 'Whirlwind Sub'."""
    s = str(name).upper()
    s = re.sub(r"\(.*?\)", " ", s)
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def poi_endpoints(poi) -> list[str]:
    """'NORTH GILA - HOODOO WASH 500 kV' -> ['NORTH GILA', 'HOODOO WASH'] (max 2)."""
    base = re.sub(r"\(.*?\)", " ", str(poi).upper())
    base = re.sub(r"\d{2,3}\s*KV.*$", "", base)
    parts = [norm_poi(p) for p in re.split(r"\s+-\s+|-(?=[A-Z])|\s+TO\s+", base) if p.strip()]
    parts = [p for p in parts if len(p) >= 3]
    return parts[:2] if parts else [norm_poi(poi)]


def poi_base(s: pd.Series) -> pd.Series:
    """Display label: strip the voltage suffix only."""
    return s.fillna("").str.upper().str.replace(r"\s*\d{2,3}\s*KV.*$", "", regex=True).str.strip()
