"""
EIA-860 — the annual federal census of generators (>= 1 MW), joined to CAISO nodes by position.

Source (public, no key): https://www.eia.gov/electricity/data/eia860/  ->  xls/eia860YYYY.zip
  data/eia860.zip    the bulk zip as published (2025 final: 13 files; we read four of them)
    2___Plant_Y*.xlsx           plant code, name, utility, county, lat/lon, balancing authority, T&D owner
    3_1_Generator_Y*.xlsx       Operable / Proposed / Retired: technology, nameplate MW, status, operating year,
                                and "RTO/ISO LMP Node Designation" — the pricing node the generator settles at
    3_4_Energy_Storage_Y*.xlsx  nameplate energy (MWh), charge/discharge MW, storage technology
    4___Owner_Y*.xlsx           owner name and percent per generator (organisations named; anything that could be a
                                person is counted, never named)

What it answers that CAISO's files cannot: who operates and owns what is ALREADY running near a node, the
technology and vintage of that capacity, and the CAISO pricing node those plants settle at — the confirmed
PNode `oasis.py` needs. What it cannot answer: the queue. EIA-860 has no point of interconnection, so the
join is BY DISTANCE to the node's mapped position (EIA_JOIN_KM), only for nodes whose position IS the substation
(exact / override / cec-line — never a line midpoint, a line end or a county centroid), and a plant on a 15-km gen-tie will land on the nearest substation whether or not
that is its POI. Every figure is labelled "within N km of the node's mapped position".

Connector contract: fetch() is the documented URL (download is done by the user or the weekly job; the
sandbox never fetches); verify() checks the zip is a zip with the four members and no executable content;
parse() reads fixed columns with a header guard; every output row carries provenance; licence in
DATA_LICENSES.md (US federal public domain).

Per-node columns added to nodes.csv:
  eia_plants            operable plants within EIA_JOIN_KM of the node position
  eia_nameplate_mw      their nameplate capacity (all technologies)
  eia_storage_mw / _mwh battery nameplate power / energy among them
  eia_tech              technology mix, e.g. "Batteries 500; Solar Photovoltaic 300"
  eia_operators         distinct utility (operator) names, up to 6
  eia_owners            distinct owner names from the Owner file, up to 6
  eia_pnodes            distinct "RTO/ISO LMP Node Designation" values — candidate PNodes for OASIS
  eia_first_year        earliest operating year among them
  eia_proposed_mw       nameplate MW in the Proposed sheet within the same radius (planned / under construction)
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA, OUT, add_provenance, csv_safe

URL = "https://www.eia.gov/electricity/data/eia860/xls/eia860{year}.zip"
ZIP = DATA / "eia860.zip"
EIA_JOIN_KM = 5.0
REAL_POSITIONS = {"exact", "override", "cec-line"}   # geo_methods that are the substation, not a proxy for it
MAX_MEMBER_BYTES = 200 * 1024 * 1024                 # zip-bomb guard: no EIA-860 member is anywhere near this
MEMBERS = {"plant": r"2___Plant_Y\d{4}\.xlsx", "gen": r"3_1_Generator_Y\d{4}\.xlsx",
           "storage": r"3_4_Energy_Storage_Y\d{4}\.xlsx", "owner": r"4___Owner_Y\d{4}\.xlsx"}
BAD_SUFFIXES = (".xlsm", ".exe", ".bat", ".cmd", ".js", ".vbs", ".ps1", ".sh", ".dll", ".scr")
BA_KEEP = {"CISO"}                      # CAISO balancing authority; blank-BA rows are not admitted
# An owner / operator name is published only if it does not read as a private individual. EIA-860's owner file
# carries a few people (small hydro, farm solar); they are counted, never named. Test: a name of two or three
# capitalised words (optionally a middle initial, or "Last, First") with no organisational token is a person.
ORG_TOKENS = ("LLC", "L.L.C", "INC", "CORP", "CORPORATION", "CO", "CO.", "COMPANY", "LP", "L.P", "LLP", "LTD", "LIMITED",
              "PLC", "PARTNERS", "PARTNERSHIP", "GROUP", "HOLDINGS", "HOLDING", "CAPITAL", "FUND", "TRUST", "BANK",
              "ENERGY", "ENERGIES", "POWER", "ELECTRIC", "UTILITY", "UTILITIES", "SOLAR", "WIND", "WINDFARM", "RENEW",
              "RENEWABLE", "RENEWABLES", "STORAGE", "GEOTHERMAL", "HYDRO", "COGENERATION", "COGEN", "DEVELOPMENT",
              "DISTRICT", "DIST", "AUTHORITY", "AGENCY", "COUNTY", "CITY", "TOWN", "STATE", "STATES", "FEDERAL",
              "BUREAU", "DEPARTMENT", "DEPT", "NAVY", "ARMY", "MARINE", "UNIVERSITY", "UNIV", "REGENTS", "COLLEGE",
              "SCHOOL", "COOPERATIVE", "CO-OP", "ASSOCIATION", "ASSOC", "FARMS", "FARM", "RANCH", "DAIRY", "VINEYARD",
              "WINERY", "INDUSTRIES", "INTERNATIONAL", "SYSTEMS", "SERVICES", "OPERATING", "OPERATIONS", "GENERATION",
              "GENERATING", "RESOURCES", "PROJECT", "PROJECTS", "VENTURES", "VENTURE", "INVESTORS", "INVESTMENT",
              "ASSET", "ASSETS", "TECHNOLOGIES", "TECHNOLOGY", "WATER", "IRRIGATION", "IRRGTN", "GAS", "OIL",
              "PETROLEUM", "REFINERY", "REFINING", "MINING", "CEMENT", "PAPER", "PRODUCTS", "FOREST", "HOSPITAL",
              "MEDICAL", "HEALTH", "CENTER", "FACILITY", "AIRPORT", "PORT", "MUNICIPAL", "MUN", "REGIONAL", "MGMT",
              "MANAGEMENT", "WASTE", "SANITATION", "TRIBE", "TRIBAL", "NATION", "BAND", "&", "GMBH", "AG", "NV", "BV",
              "AB", "STUDIO", "STUDIOS", "MOTORS", "GLOBAL", "AMERICA", "AMERICAN", "NATIONAL", "PACIFIC",
              "INCORPORATED", "WHOLESALE", "COMMUNICATIONS", "FOODS", "FARMING", "FINANCE", "COMPANIES", "SERVICE")
_ORG_RE = re.compile(r"(?<![A-Z0-9])(?:" + "|".join(re.escape(t) for t in ORG_TOKENS) + r")(?![A-Z0-9])")
_PARTICLES = {"van", "der", "de", "la", "le", "di", "da", "del", "den", "von", "mc", "mac", "st", "y", "e", "du", "of", "the"}
_NAME_TOKEN = re.compile(r"^(?:[A-Z][a-z'\-]*\.?|[A-Z]\.?|Jr\.?|Sr\.?|II|III|IV)$")


def is_org(name: str) -> bool:
    """False for anything that could be a private individual: no organisational token AND two to five
    name-like tokens, two to six of them (capitalised words, initials, particles such as van/der/de, Jr/III). Brands with a single
    word or with any org token stay. Over-blocking a company costs a name; under-blocking costs a person."""
    n = str(name).strip()
    if not n:
        return False
    if _ORG_RE.search(n.upper()):
        return True
    n = n.replace(",", " ")
    toks = n.split()
    if not 2 <= len(toks) <= 6:
        return True
    return not all(_NAME_TOKEN.match(t) or t.lower() in _PARTICLES for t in toks)


def org_only(names) -> tuple[list[str], int]:
    """(organisation names, number of withheld individual/other names)."""
    vals = [str(v).strip() for v in names if str(v).strip() and str(v).strip().lower() != "nan"]
    keep = [v for v in vals if is_org(v)]
    return keep, len(vals) - len(keep)


EIA_COLS = ["eia_plants", "eia_nameplate_mw", "eia_storage_mw", "eia_storage_mwh", "eia_tech", "eia_operators",
            "eia_owners", "eia_pnodes", "eia_first_year", "eia_proposed_mw"]


def fetch_url(year: int) -> str:
    return URL.format(year=year)


def verify(path: Path = ZIP) -> dict:
    """The zip is a zip, holds the four members we read, and nothing executable. Returns member names + year."""
    if not zipfile.is_zipfile(path):
        raise ValueError(f"{path.name}: not a zip file")
    z = zipfile.ZipFile(path)
    names = z.namelist()
    bad = [n for n in names if n.lower().endswith(BAD_SUFFIXES)]
    if bad:
        raise ValueError(f"{path.name}: executable content in zip: {bad}")
    big = [(i.filename, i.file_size) for i in z.infolist() if i.file_size > MAX_MEMBER_BYTES
           or (i.compress_size and i.file_size / i.compress_size > 200)]
    if big:
        raise ValueError(f"{path.name}: implausible member size / compression ratio: {big}")
    found = {}
    for key, pat in MEMBERS.items():
        m = [n for n in names if re.fullmatch(pat, n)]
        if not m:
            raise ValueError(f"{path.name}: no member matching {pat}")
        found[key] = m[0]
    year = int(re.search(r"Y(\d{4})", found["plant"]).group(1))
    return {"members": found, "year": year, "bytes": path.stat().st_size}


def _read(z: zipfile.ZipFile, member: str, sheet=0, required: tuple[str, ...] = ()) -> pd.DataFrame:
    raw = pd.read_excel(io.BytesIO(z.read(member)), sheet_name=sheet, header=None, nrows=4, dtype=str)
    hdr = next((i for i, row in raw.iterrows() if "Plant Code" in row.astype(str).values), 1)
    df = pd.read_excel(io.BytesIO(z.read(member)), sheet_name=sheet, header=hdr, dtype=str)
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{member}[{sheet}]: header drift — missing {missing}")
    return df


def load(path: Path = ZIP) -> dict[str, pd.DataFrame]:
    """Plants (CAISO footprint), operable generators, proposed generators, storage, owners — as clean frames."""
    info = verify(path)
    z = zipfile.ZipFile(path)
    m = info["members"]
    plant = _read(z, m["plant"], required=("Plant Code", "Plant Name", "Utility Name", "State", "County", "Latitude",
                                          "Longitude", "Balancing Authority Code"))
    plant = plant.rename(columns={"Plant Code": "plant_code", "Plant Name": "plant_name", "Utility Name": "utility_name",
                                  "State": "state", "County": "county", "Latitude": "lat", "Longitude": "lon",
                                  "Balancing Authority Code": "ba",
                                  "Transmission or Distribution System Owner": "td_owner"})
    plant["ba"] = plant.ba.fillna("").str.strip()
    plant = plant[plant.ba.isin(BA_KEEP)].copy()          # blank-BA rows are retired/other-BA plants; not ours
    plant["lat"] = pd.to_numeric(plant.lat, errors="coerce")
    plant["lon"] = pd.to_numeric(plant.lon, errors="coerce")
    plant = plant.dropna(subset=["lat", "lon"])
    keep = ["plant_code", "plant_name", "utility_name", "state", "county", "lat", "lon", "ba"]
    if "td_owner" in plant:
        keep.append("td_owner")
    plant = plant[keep]

    gen_cols = ("Plant Code", "Generator ID", "Technology", "Nameplate Capacity (MW)", "Status")
    gen = _read(z, m["gen"], sheet="Operable", required=gen_cols)
    prop = _read(z, m["gen"], sheet="Proposed", required=gen_cols)
    for df in (gen, prop):
        df.rename(columns={"Plant Code": "plant_code", "Generator ID": "generator_id", "Technology": "technology",
                           "Prime Mover": "prime_mover", "Nameplate Capacity (MW)": "nameplate_mw", "Status": "status",
                           "Operating Year": "operating_year", "RTO/ISO LMP Node Designation": "lmp_node",
                           "Utility Name": "utility_name"}, inplace=True)
        df["nameplate_mw"] = pd.to_numeric(df.nameplate_mw, errors="coerce")
        for c in ("operating_year", "lmp_node", "prime_mover", "utility_name"):
            if c not in df:
                df[c] = ""
    gen = gen[gen.plant_code.isin(plant.plant_code)]
    prop = prop[prop.plant_code.isin(plant.plant_code)]

    stor = _read(z, m["storage"], sheet="Operable", required=("Plant Code", "Generator ID", "Nameplate Capacity (MW)"))
    stor = stor.rename(columns={"Plant Code": "plant_code", "Generator ID": "generator_id",
                                "Nameplate Capacity (MW)": "storage_mw", "Nameplate Energy Capacity (MWh)": "storage_mwh"})
    if "storage_mwh" not in stor:
        stor["storage_mwh"] = float("nan")
    stor["storage_mw"] = pd.to_numeric(stor.storage_mw, errors="coerce")
    stor["storage_mwh"] = pd.to_numeric(stor.storage_mwh, errors="coerce")
    stor = stor[stor.plant_code.isin(plant.plant_code)][["plant_code", "generator_id", "storage_mw", "storage_mwh"]]

    own = _read(z, m["owner"], required=("Plant Code", "Owner Name"))
    own = own.rename(columns={"Plant Code": "plant_code", "Owner Name": "owner_name", "Percent Owned": "pct"})
    own = own[own.plant_code.isin(plant.plant_code)][["plant_code", "owner_name"]].drop_duplicates()

    src = Path(path).name
    return {"year": info["year"], "plant": add_provenance(plant.copy(), src), "gen": add_provenance(gen.copy(), src),
            "proposed": add_provenance(prop.copy(), src), "storage": add_provenance(stor.copy(), src),
            "owner": add_provenance(own.copy(), src)}


def _haversine_vec(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    r = np.pi / 180
    a = (0.5 - np.cos((lat2 - lat1) * r) / 2
         + np.cos(lat1 * r) * np.cos(lat2 * r) * (1 - np.cos((lon2 - lon1) * r)) / 2)
    return 12742 * np.arcsin(np.sqrt(a))


def _join_plants_to_nodes(plant: pd.DataFrame, nodes: pd.DataFrame, km: float = EIA_JOIN_KM) -> pd.Series:
    """Nearest positioned node within `km` for every plant (NaN when none). Vectorised per plant over the
    ~500 positioned nodes; 2,000 x 500 haversines is nothing."""
    pos = nodes[nodes.lat.notna() & nodes.lon.notna()]
    if "geo_method" in pos:
        # only positions that are the substation itself: a line midpoint is not a place, a line end shares the
        # substation's coordinates (and would win the tie by row order), a centroid is a county
        pos = pos[pos.geo_method.isin(REAL_POSITIONS)]
    out = pd.Series(index=plant.index, dtype=object)
    if pos.empty:
        return out
    nl, no = pos.lat.to_numpy(), pos.lon.to_numpy()
    keys = pos.node_key.to_numpy()
    for i, la, lo in zip(plant.index, plant.lat, plant.lon, strict=True):
        d = _haversine_vec(la, lo, nl, no)
        j = d.argmin()
        if d[j] <= km:
            out.at[i] = keys[j]
    return out


def per_node(frames: dict[str, pd.DataFrame], nodes: pd.DataFrame, km: float = EIA_JOIN_KM) -> pd.DataFrame:
    plant = frames["plant"].copy()
    plant["node_key"] = _join_plants_to_nodes(plant, nodes, km)
    hit = plant.dropna(subset=["node_key"])
    if hit.empty:
        return pd.DataFrame(columns=EIA_COLS)
    gen = frames["gen"].merge(hit[["plant_code", "node_key", "utility_name"]].rename(columns={"utility_name": "op"}),
                              on="plant_code")
    stor = frames["storage"].merge(hit[["plant_code", "node_key"]], on="plant_code")
    own = frames["owner"].merge(hit[["plant_code", "node_key"]], on="plant_code")
    prop = frames["proposed"].merge(hit[["plant_code", "node_key"]], on="plant_code")

    def tech_mix(s: pd.DataFrame) -> str:
        t = s.groupby("technology").nameplate_mw.sum().sort_values(ascending=False)
        return "; ".join(f"{k} {v:,.0f}" for k, v in t.items() if v > 0)

    def uniq(s: pd.Series, n: int = 6) -> str:
        vals = [v for v in s.fillna("").astype(str).str.strip().unique() if v and v.lower() != "nan"]
        return "; ".join(sorted(vals)[:n]) + (" …" if len(vals) > n else "")

    def uniq_org(s: pd.Series, n: int = 6) -> str:
        keep, withheld = org_only(s.fillna("").astype(str).str.strip().unique())
        keep = sorted(set(keep))
        txt = "; ".join(keep[:n]) + (" …" if len(keep) > n else "")
        if withheld:
            txt += f"{'; ' if txt else ''}{withheld} individual owner{'s' if withheld != 1 else ''} not named"
        return txt

    if gen.empty and prop.empty:
        return pd.DataFrame(columns=EIA_COLS)
    g = gen.groupby("node_key")
    empty = pd.Series(dtype=object)
    out = pd.DataFrame({
        # plants that have at least one OPERABLE generator (a retired-only or proposed-only plant is not "operating")
        "eia_plants": g.plant_code.nunique() if len(gen) else empty,
        "eia_nameplate_mw": g.nameplate_mw.sum().round(1) if len(gen) else empty,
        "eia_storage_mw": stor.groupby("node_key").storage_mw.sum().round(1),
        "eia_storage_mwh": stor.groupby("node_key").storage_mwh.sum().round(1),
        "eia_tech": (gen.groupby("node_key")[["technology", "nameplate_mw"]].apply(tech_mix) if len(gen) else empty),
        "eia_operators": g.op.apply(uniq_org) if len(gen) else empty,
        "eia_owners": own[own.plant_code.isin(gen.plant_code)].groupby("node_key").owner_name.apply(uniq_org),
        "eia_pnodes": g.lmp_node.apply(uniq) if len(gen) else empty,
        "eia_first_year": (g.operating_year.apply(lambda s: pd.to_numeric(s, errors="coerce").min())
                           if len(gen) else empty),
        "eia_proposed_mw": prop.groupby("node_key").nameplate_mw.sum().round(1),
    })
    out = out.reindex(columns=EIA_COLS)
    for c in ("eia_plants", "eia_nameplate_mw", "eia_storage_mw", "eia_storage_mwh", "eia_proposed_mw"):
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    for c in ("eia_tech", "eia_operators", "eia_owners", "eia_pnodes"):
        out[c] = out[c].fillna("")
    out.index.name = "node_key"
    return out


def join(nodes: pd.DataFrame, withheld: bool = False, path: Path = ZIP) -> pd.DataFrame:
    # NaN, not 0.0: "we have no EIA file" must not render as "nothing operates near this node".
    for c in EIA_COLS:
        nodes[c] = "" if c in ("eia_tech", "eia_operators", "eia_owners", "eia_pnodes") else float("nan")
    nodes["eia_first_year"] = float("nan")
    if withheld:
        print("eia860: withheld by the freshness gate — EIA columns are blank (not zero)")
        return nodes
    if not Path(path).exists():
        print(f"eia860: {path} absent — EIA columns blank (download: {fetch_url(2025)})")
        return nodes
    try:
        frames = load(path)
    except (ValueError, zipfile.BadZipFile, KeyError) as e:      # corrupt / partial / drifted file: never fail nodes
        print(f"eia860: {path.name} unusable ({e}) — EIA columns empty", file=sys.stderr)
        return nodes
    pn = per_node(frames, nodes)
    OUT.mkdir(exist_ok=True)
    plant = frames["plant"].copy()
    plant["node_key"] = _join_plants_to_nodes(plant, nodes)
    csv_safe(plant).to_csv(OUT / "eia860_plants.csv", index=False)
    csv_safe(pn.reset_index()).to_csv(OUT / "eia860_by_node.csv", index=False)
    nodes = nodes.drop(columns=EIA_COLS).merge(pn, left_on="node_key", right_index=True, how="left")
    for c in ("eia_plants", "eia_nameplate_mw", "eia_storage_mw", "eia_storage_mwh", "eia_proposed_mw"):
        nodes[c] = nodes[c].fillna(0.0)
    for c in ("eia_tech", "eia_operators", "eia_owners", "eia_pnodes"):
        nodes[c] = nodes[c].fillna("")
    hit = nodes.eia_plants > 0
    print(f"eia860 ({frames['year']}): {len(frames['plant'])} CAISO-footprint plants; {int(plant.node_key.notna().sum())} "
          f"within {EIA_JOIN_KM:.0f} km of a positioned node; {hit.sum()} nodes get EIA columns "
          f"({nodes.loc[hit, 'eia_nameplate_mw'].sum():,.0f} MW nameplate, {nodes.loc[hit, 'eia_storage_mwh'].sum():,.0f} MWh storage); "
          f"{(nodes.eia_pnodes != '').sum()} nodes carry a reported LMP node")
    return nodes


def main() -> None:
    if not ZIP.exists():
        sys.exit(f"{ZIP} missing. Download {fetch_url(2025)} and save it as data/eia860.zip (no key needed).")
    info = verify(ZIP)
    frames = load(ZIP)
    print(f"EIA-860 {info['year']}: {len(frames['plant'])} plants in the CAISO footprint, "
          f"{len(frames['gen'])} operable generators ({frames['gen'].nameplate_mw.sum():,.0f} MW), "
          f"{len(frames['proposed'])} proposed ({frames['proposed'].nameplate_mw.sum():,.0f} MW), "
          f"{len(frames['storage'])} storage units ({frames['storage'].storage_mwh.sum():,.0f} MWh)")
    print(frames["gen"].groupby("technology").nameplate_mw.sum().sort_values(ascending=False).head(10).round(0).to_string())
    nodes_path = OUT / "nodes.csv"
    if nodes_path.exists():
        nodes = pd.read_csv(nodes_path, dtype={"node_key": str, "geo_method": str})
        pn = per_node(frames, nodes)
        print(f"\n{len(pn)} nodes with EIA plants within {EIA_JOIN_KM:.0f} km; top 12 by nameplate:")
        print(pn.sort_values("eia_nameplate_mw", ascending=False).head(12)[
            ["eia_plants", "eia_nameplate_mw", "eia_storage_mwh", "eia_pnodes"]].to_string())


if __name__ == "__main__":
    main()
