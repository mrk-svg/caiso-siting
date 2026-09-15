"""eia860.py: EIA-860 bulk zip -> plants near CAISO nodes (by distance), owners, storage MWh, LMP nodes."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from caiso_siting import eia860

PLANT_HDR = ["Utility ID", "Utility Name", "Plant Code", "Plant Name", "Street Address", "City", "State", "Zip",
             "County", "Latitude", "Longitude", "NERC Region", "Balancing Authority Code",
             "Transmission or Distribution System Owner"]
GEN_HDR = ["Utility ID", "Utility Name", "Plant Code", "Plant Name", "State", "County", "Generator ID", "Technology",
           "Prime Mover", "RTO/ISO LMP Node Designation", "Nameplate Capacity (MW)", "Status", "Operating Year"]
ES_HDR = ["Utility ID", "Utility Name", "Plant Code", "Plant Name", "Generator ID", "Status", "Technology",
          "Nameplate Capacity (MW)", "Nameplate Energy Capacity (MWh)"]
OWN_HDR = ["Utility ID", "Utility Name", "Plant Code", "Plant Name", "State", "Generator ID", "Status", "Owner Name",
           "Percent Owned"]


def xlsx(sheets: dict[str, tuple[list[str], list[list]]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, (hdr, rows) in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(["Form EIA-860 title row"])          # EIA's title row above the header
        ws.append(hdr)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def write_zip(path: Path, extra_member: str | None = None) -> Path:
    plants = [
        [1, "Op A Energy LLC", "100", "Whirlwind Solar", "", "", "CA", "", "Kern", 35.0, -118.3, "WECC", "CISO", "SCE"],
        [2, "Op B", "200", "Far Plant", "", "", "CA", "", "Kern", 36.5, -119.9, "WECC", "CISO", "PG&E"],
        [3, "Op C Wind Co", "300", "Nevada Plant", "", "", "NV", "", "Clark", 35.01, -118.31, "WECC", "CISO", ""],
        [5, "Op E Power Co", "500", "Blank BA Plant", "", "", "CA", "", "Kern", 35.003, -118.303, "WECC", "", ""],  # blank BA: dropped
        [6, "Op F Gas Co", "600", "Retired Only", "", "", "CA", "", "Kern", 35.004, -118.304, "WECC", "CISO", ""],   # no operable unit
        [4, "Op D", "400", "Texas Plant", "", "", "TX", "", "Harris", 29.7, -95.3, "TRE", "ERCO", ""],    # dropped
    ]
    gens = [
        [1, "Op A", "100", "Whirlwind Solar", "CA", "Kern", "G1", "Solar Photovoltaic", "PV", "WHIRL_2_SOLAR1", 100, "OP", 2015],
        [1, "Op A", "100", "Whirlwind Solar", "CA", "Kern", "G2", "Batteries", "BA", "WHIRL_2_SOLAR1", 50, "OP", 2022],
        [3, "Op C", "300", "Nevada Plant", "NV", "Clark", "G1", "Onshore Wind Turbine", "WT", "", 30, "OP", 2010],
        [2, "Op B", "200", "Far Plant", "CA", "Kern", "G1", "Natural Gas Fired Combined Cycle", "CA", "", 500, "OP", 2001],
        [4, "Op D", "400", "Texas Plant", "TX", "Harris", "G1", "Natural Gas Fired Combined Cycle", "CA", "", 900, "OP", 2001],
        [5, "Op E Power Co", "500", "Blank BA Plant", "CA", "Kern", "G1", "Solar Photovoltaic", "PV", "", 70, "OP", 2019],
    ]
    proposed = [[1, "Op A", "100", "Whirlwind Solar", "CA", "Kern", "G3", "Batteries", "BA", "", 80, "P", 2027]]
    stor = [[1, "Op A", "100", "Whirlwind Solar", "G2", "OP", "Batteries", 50, 200]]
    owners = [[1, "Op A", "100", "Whirlwind Solar", "CA", "G1", "OP", "Owner One LLC", 100],
              [1, "Op A", "100", "Whirlwind Solar", "CA", "G2", "OP", "Owner Two Inc", 100],
              [3, "Op C", "300", "Nevada Plant", "NV", "G1", "OP", "Alan L. Boyce", 100],          # an individual: never named
              [4, "Op D", "400", "Texas Plant", "TX", "G1", "OP", "Texan Co", 100]]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("2___Plant_Y2025.xlsx", xlsx({"Plant": (PLANT_HDR, plants)}))
        z.writestr("3_1_Generator_Y2025.xlsx", xlsx({"Operable": (GEN_HDR, gens), "Proposed": (GEN_HDR, proposed),
                                                     "Retired and Canceled": (GEN_HDR, [])}))
        z.writestr("3_4_Energy_Storage_Y2025.xlsx", xlsx({"Operable": (ES_HDR, stor), "Proposed": (ES_HDR, [])}))
        z.writestr("4___Owner_Y2025.xlsx", xlsx({"Owner": (OWN_HDR, owners)}))
        z.writestr("LayoutY2025.xlsx", xlsx({"Layout": (["a"], [])}))
        if extra_member:
            z.writestr(extra_member, b"x")
    return path


NODES = pd.DataFrame({
    "node_key": ["WHIRLWIND", "GATES", "CENTROID", "NOPOS", "SOME LINE", "WHIRLWIND END"],
    "lat": [35.002, 36.0, 36.5, float("nan"), 35.0021, 35.002],
    "lon": [-118.302, -120.0, -119.9, float("nan"), -118.3021, -118.302],
    # SOME LINE is a midpoint 15 m from the plant; WHIRLWIND END shares WHIRLWIND's coordinates exactly and sorts
    # after it — neither may capture the plants
    "geo_method": ["exact", "exact", "county-centroid", "none", "line-midpoint", "line-one-end"],
})


def test_verify_accepts_the_bulk_layout_and_rejects_executables(tmp_path):
    info = eia860.verify(write_zip(tmp_path / "eia860.zip"))
    assert info["year"] == 2025 and set(info["members"]) == {"plant", "gen", "storage", "owner"}
    with pytest.raises(ValueError, match="executable"):
        eia860.verify(write_zip(tmp_path / "bad.zip", extra_member="macro.xlsm"))
    (tmp_path / "notzip.zip").write_bytes(b"hello")
    with pytest.raises(ValueError, match="not a zip"):
        eia860.verify(tmp_path / "notzip.zip")


def test_load_keeps_caiso_footprint_only_and_reads_lmp_nodes(tmp_path):
    f = eia860.load(write_zip(tmp_path / "eia860.zip"))
    assert set(f["plant"].plant_code) == {"100", "200", "300", "600"}   # ERCOT and blank-BA plants dropped
    assert set(f["gen"].plant_code) == {"100", "200", "300"}
    assert f["gen"].loc[f["gen"].generator_id == "G1", "lmp_node"].iloc[0] == "WHIRL_2_SOLAR1"
    assert f["storage"].storage_mwh.sum() == 200
    assert set(f["owner"].owner_name) == {"Owner One LLC", "Owner Two Inc", "Alan L. Boyce"}
    assert (f["plant"].source_file == "eia860.zip").all()


def test_per_node_joins_by_distance_to_positioned_nodes_only(tmp_path):
    f = eia860.load(write_zip(tmp_path / "eia860.zip"))
    pn = eia860.per_node(f, NODES)
    w = pn.loc["WHIRLWIND"]
    assert w.eia_plants == 2                                   # 100 and 300 (operable); 600 is retired-only; 200 is 190 km away
    assert "SOME LINE" not in pn.index and "WHIRLWIND END" not in pn.index
    assert w.eia_nameplate_mw == 180 and w.eia_storage_mw == 50 and w.eia_storage_mwh == 200
    assert w.eia_tech.startswith("Solar Photovoltaic 100")
    assert "Op A Energy LLC" in w.eia_operators and "Op C Wind Co" in w.eia_operators
    assert w.eia_owners == "Owner One LLC; Owner Two Inc; 1 individual owner not named"
    assert "Boyce" not in w.eia_owners
    assert w.eia_pnodes == "WHIRL_2_SOLAR1"
    assert w.eia_first_year == 2010 and w.eia_proposed_mw == 80
    assert "CENTROID" not in pn.index                          # plant 200 sits on the centroid but centroids never join
    assert set(pn.index) == {"WHIRLWIND"}
    assert "GATES" not in pn.index and "NOPOS" not in pn.index


def test_join_adds_columns_fills_zero_and_writes_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(eia860, "OUT", tmp_path)
    out = eia860.join(NODES.copy(), write_zip(tmp_path / "eia860.zip"))
    assert list(c for c in eia860.EIA_COLS if c in out.columns) == eia860.EIA_COLS
    assert out.set_index("node_key").loc["GATES", "eia_plants"] == 0
    assert out.set_index("node_key").loc["GATES", "eia_pnodes"] == ""
    assert (tmp_path / "eia860_plants.csv").exists() and (tmp_path / "eia860_by_node.csv").exists()
    assert "nodes get EIA columns" in capsys.readouterr().out


def test_join_tolerates_a_corrupt_or_partial_zip(tmp_path, capsys):
    bad = tmp_path / "eia860.zip"
    bad.write_bytes(b"<html>503 Service Unavailable</html>")
    out = eia860.join(NODES.copy(), bad)
    assert (out.eia_plants == 0).all() and "unusable" in capsys.readouterr().err
    good = write_zip(tmp_path / "good.zip").read_bytes()
    (tmp_path / "trunc.zip").write_bytes(good[: len(good) // 2])
    out = eia860.join(NODES.copy(), tmp_path / "trunc.zip")
    assert (out.eia_plants == 0).all()


def test_verify_rejects_implausible_member_sizes(tmp_path, monkeypatch):
    monkeypatch.setattr(eia860, "MAX_MEMBER_BYTES", 1000)
    with pytest.raises(ValueError, match="implausible"):
        eia860.verify(write_zip(tmp_path / "eia860.zip"))


def test_per_node_with_matched_plants_but_no_operable_generators(tmp_path):
    f = eia860.load(write_zip(tmp_path / "eia860.zip"))
    f["gen"] = f["gen"].iloc[0:0]
    pn = eia860.per_node(f, NODES)
    assert "WHIRLWIND" in pn.index and pn.loc["WHIRLWIND", "eia_plants"] == 0
    assert pn.loc["WHIRLWIND", "eia_proposed_mw"] == 80


def test_join_without_zip_leaves_columns_empty(tmp_path, capsys):
    out = eia860.join(NODES.copy(), tmp_path / "absent.zip")
    assert (out.eia_plants == 0).all() and (out.eia_pnodes == "").all()
    assert "absent" in capsys.readouterr().out


@pytest.mark.real_data
def test_real_zip_if_present():
    if not eia860.ZIP.exists():
        pytest.skip("data/eia860.zip not downloaded")
    info = eia860.verify(eia860.ZIP)
    f = eia860.load(eia860.ZIP)
    assert info["year"] >= 2024
    assert len(f["plant"]) > 1500 and f["gen"].nameplate_mw.sum() > 80_000
    assert f["storage"].storage_mwh.sum() > 20_000
    assert (f["gen"].lmp_node != "").mean() > 0.3          # most CAISO generators report a pricing node


def test_individuals_are_never_named():
    assert eia860.is_org("Pacific Gas & Electric Co.") and eia860.is_org("Alta Wind II, LLC")
    assert eia860.is_org("City of Anaheim") and eia860.is_org("Imperial Irrigation District")
    assert not eia860.is_org("Alan L. Boyce") and not eia860.is_org("Maria Gonzalez")
    assert not eia860.is_org("Abigail Sanchez") and not eia860.is_org("Gaston Novak")   # AB / AG / NV only as whole words
    assert not eia860.is_org("Boyce, Alan L.")
    assert not eia860.is_org("Pier Van Der Hoek") and not eia860.is_org("Mary Ann de la Cruz Jr.")
    assert not eia860.is_org("Wells Fargo")          # over-block is acceptable; a leaked person is not
    for brand in ("Starbucks", "Yahoo!", "Intel", "Southern California Edison Co", "U S Bureau of Reclamation",
                  "Kings River Conservation Dist", "The Regents of the Univ. of California", "Qualcomm Incorporated"):
        assert eia860.is_org(brand), brand
    keep, withheld = eia860.org_only(["Boralex US Operations LLC", "John Smith", "", "nan"])
    assert keep == ["Boralex US Operations LLC"] and withheld == 1
