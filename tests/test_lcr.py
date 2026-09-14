"""lcr.py: Local Capacity Area membership per node from data/lcr_areas.csv."""
from __future__ import annotations

import pandas as pd
import pytest

from caiso_siting import lcr

HEADER = "substation,utility,lcr_area,lcr_sub_area,relation,note,source,source_date\n"
SRC = "Final 2027 LCT Report,2026-04-29"


def write(path, rows: str):
    path.write_text("# comment line\n" + HEADER + rows)
    return path


def test_missing_or_empty_file_gives_empty_frame_with_columns(tmp_path):
    assert list(lcr.load(tmp_path / "nope.csv").columns) == ["node_key", "utility", *lcr.LCR_COLS]
    p = write(tmp_path / "lcr_areas.csv", "")
    assert lcr.load(p).empty


def test_in_and_out_rows_and_the_queue_node_key(tmp_path):
    p = write(tmp_path / "lcr_areas.csv",
              f"MOSS LANDING SUBSTATION 500KV,PGAE,Greater Bay Area,South Bay-Moss Landing,in,,{SRC}\n"
              f"Gates,PGAE,Greater Fresno,,out,only the 70 kV bus is in,{SRC}\n"
              f"Sobrante,PGAE,North Coast/North Bay,,out,,{SRC}\n"          # same station: out of one area...
              f"Sobrante,PGAE,Greater Bay Area,,in,,{SRC}\n"                # ...inside another: in wins
              f" ,PGAE,Kern,,in,,{SRC}\n")                                  # blank substation: dropped
    df = lcr.load(p).set_index("node_key")
    assert len(df) == 3
    assert df.loc["MOSS LANDING", "lcr_area"] == "Greater Bay Area"
    assert df.loc["MOSS LANDING", "lcr_status"] == "in Greater Bay Area"
    assert df.loc["MOSS LANDING", "lcr_sub_area"] == "South Bay-Moss Landing"
    assert df.loc["GATES", "lcr_area"] == "" and df.loc["GATES", "lcr_status"] == "outside Greater Fresno"
    assert df.loc["GATES", "lcr_note"] == "only the 70 kV bus is in"
    assert df.loc["SOBRANTE", "lcr_status"] == "in Greater Bay Area"
    assert (df.lcr_source == "Final 2027 LCT Report [2026-04-29]").all()


def test_utility_disambiguates_same_name_stations(tmp_path):
    p = write(tmp_path / "lcr_areas.csv",
              f"Eagle Rock,PGAE,North Coast/North Bay,,in,,{SRC}\n"
              f"Eagle Rock,SCE,LA Basin,,in,,{SRC}\n"
              f"Lugo,,LA Basin,,out,,{SRC}\n")
    nodes = pd.DataFrame({"node_key": ["EAGLE ROCK", "EAGLE ROCK", "LUGO", "LUGO", "WHIRLWIND"],
                          "utility": ["PGAE", "SCE", "SCE", "", "SCE"]})
    out = lcr.join(nodes, p)
    assert out.lcr_area.tolist() == ["North Coast/North Bay", "LA Basin", "", "", ""]
    assert out.lcr_status.tolist() == ["in North Coast/North Bay", "in LA Basin", "outside LA Basin",
                                       "outside LA Basin", ""]   # blank utility in the file matches any node


def test_join_without_rows_prints_and_blanks(tmp_path, capsys):
    nodes = pd.DataFrame({"node_key": ["GATES"], "utility": ["PGAE"]})
    out = lcr.join(nodes, tmp_path / "absent.csv")
    assert (out[lcr.LCR_COLS] == "").all().all()
    assert "no rows" in capsys.readouterr().out


def test_bad_header_or_relation_is_an_error(tmp_path):
    p = tmp_path / "lcr_areas.csv"
    p.write_text("substation,area\nGATES,Greater Fresno\n")
    with pytest.raises(ValueError):
        lcr.load(p)
    write(p, f"Gates,PGAE,Greater Fresno,,inside,,{SRC}\n")
    with pytest.raises(ValueError):
        lcr.load(p)


@pytest.mark.real_data
def test_shipped_file_loads_and_names_the_bulk_stations():
    df = lcr.load().set_index("node_key")
    assert len(df) > 100
    for k in ("LUGO", "TESLA", "VINCENT", "GATES", "MIDWAY", "RED BLUFF"):
        assert df.loc[k, "lcr_status"].startswith("outside"), k
    for k, area in (("MOSS LANDING", "Greater Bay Area"), ("RIO HONDO", "LA Basin"), ("TRANQUILITY", "Greater Fresno"),
                    ("IMPERIAL VALLEY", "San Diego-Imperial Valley"), ("DEVERS", "LA Basin")):
        assert df.loc[k, "lcr_area"] == area, k
    assert (df.lcr_source == "Final 2027 LCT Report [2026-04-29]").all()
