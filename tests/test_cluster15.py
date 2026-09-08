"""cluster15.py against a synthetic workbook with CAISO's Cluster 15 layout (sheet 'Cluster 15 '
with a trailing space, header in row 1), plus a smoke test on the real file."""
from __future__ import annotations

import pandas as pd
import pytest
from conftest import C15_REQUIRED, assert_required_columns, write_cluster15_xlsx

from caiso_siting import cluster15


@pytest.fixture
def c15(cluster15_xlsx) -> pd.DataFrame:
    return cluster15.load(cluster15_xlsx)


def test_sheet_names_with_trailing_space_are_found(c15):
    assert c15.sheet_status.value_counts().to_dict() == {"ACTIVE": 3, "WITHDRAWN": 2}


def test_lower_case_sheet_names_also_found(tmp_path):
    df = cluster15.load(write_cluster15_xlsx(tmp_path / "c.xlsx", sheet_names=("cluster 15", "WITHDRAWN ")))
    assert len(df) == 5


def test_missing_sheet_exits_with_message(tmp_path):
    path = write_cluster15_xlsx(tmp_path / "bad.xlsx", sheet_names=("Sheet1", "Withdrawn"))
    with pytest.raises(SystemExit, match="CLUSTER 15"):
        cluster15.load(path)


def test_header_whitespace_is_stripped(c15):
    # 'Queue Date ' (active sheet) and 'Application Date ' (withdrawn sheet) carry trailing spaces
    assert "queue_date" in c15.columns and "request_received" in c15.columns
    assert c15.queue_date.notna().all()
    assert c15.request_received.notna().all()
    assert "Queue Date " not in c15.columns and "Application Date " not in c15.columns


def test_canonical_columns_present(c15):
    assert_required_columns(c15, C15_REQUIRED)


def test_deliverability_mapping(c15):
    by = c15.set_index("project_name")
    assert by.loc["Alisa Solar Energy Complex 2", "deliverability"] == "ENERGY ONLY (REQ)"
    assert by.loc["Annapurna", "deliverability"] == "FULL CAPACITY (REQ)"
    assert by.loc["Whirlwind Storage", "deliverability"] == "FULL CAPACITY (REQ)"   # merchant variant
    assert by.loc["Clay Flats", "deliverability"] == "ENERGY ONLY (REQ)"
    assert set(c15.deliverability) == {"ENERGY ONLY (REQ)", "FULL CAPACITY (REQ)"}
    assert by.loc["Whirlwind Storage", "is_merchant"] and not by.loc["Annapurna", "is_merchant"]
    assert by.loc["Amargosa SEZ", "is_merchant"]


def test_county_cleanup(c15):
    by = c15.set_index("project_name")
    assert by.loc["Annapurna", "county"] == "MERCED"                # "Merced County"
    assert by.loc["Clay Flats", "county"] == "KINGS"                # "king"
    assert by.loc["Whirlwind Storage", "county"] == "SAN BERNARDINO"  # "San Bernadino"
    assert by.loc["Alisa Solar Energy Complex 2", "county"] == "YUMA"


def test_numeric_coercion_with_na_strings(c15):
    by = c15.set_index("project_name")
    assert pd.isna(by.loc["Annapurna", "mw_2"])          # "N/A" -> NaN
    assert pd.isna(by.loc["Annapurna", "mw_3"])
    assert by.loc["Annapurna", "mw_1"] == 257.0
    assert by.loc["Annapurna", "net_mw"] == 250.0
    assert by.loc["Alisa Solar Energy Complex 2", "poi_kv"] == 525.0
    assert by.loc["Clay Flats", "mw_1"] == pytest.approx(437.08)


def test_storage_mw_and_flags(c15):
    by = c15.set_index("project_name")
    assert by.loc["Alisa Solar Energy Complex 2", "storage_mw"] == 500.0    # fuel 2 = Storage/Battery
    assert by.loc["Alisa Solar Energy Complex 2", "has_solar"]
    assert not by.loc["Alisa Solar Energy Complex 2", "is_standalone_storage"]
    # component nameplate is kept raw; storage_mw is capped at net-to-grid
    assert by.loc["Annapurna", "storage_component_mw"] == 257.0
    assert by.loc["Annapurna", "storage_mw"] == 250.0                       # net_mw 250 caps the 257 MW battery
    assert by.loc["Annapurna", "is_standalone_storage"]
    assert by.loc["Amargosa SEZ", "storage_component_mw"] == pytest.approx(508.19)
    assert by.loc["Amargosa SEZ", "storage_mw"] == 500.0                    # net_mw 500
    assert by.loc["Alisa Solar Energy Complex 2", "storage_component_mw"] == 500.0
    assert (c15.storage_mw <= c15.net_mw).all()
    assert (c15.storage_mw <= c15.storage_component_mw).all()


def test_cluster_labels_and_constants(c15):
    assert (c15.cluster == "C15").all()
    assert (c15.study_process == "C15").all()
    assert (~c15.withdrew_post_phase2).all()
    assert c15.poi_mw.equals(c15.net_mw)


def test_dates_and_years(c15):
    by = c15.set_index("project_name")
    assert by.loc["Clay Flats", "withdrawn_date"] == pd.Timestamp("2025-04-23")
    assert by.loc["Clay Flats", "withdrawn_year"] == 2025
    assert pd.isna(by.loc["Annapurna", "withdrawn_date"])
    assert (c15.queue_year == 2025).all()


def test_poi_keys_join_with_public_report(c15):
    by = c15.set_index("project_name")
    assert by.loc["Whirlwind Storage", "node_key"] == "WHIRLWIND"     # same key queue_report produces
    assert by.loc["Whirlwind Storage", "poi_base"] == "WHIRLWIND"
    assert by.loc["Annapurna", "node_key"] == "QUINTO"
    assert by.loc["Alisa Solar Energy Complex 2", "node_key"] == "NORTH GILA HOODOO WASH"
    assert by.loc["Alisa Solar Energy Complex 2", "poi_base"] == "NORTH GILA - HOODOO WASH (SDGE PORTION ONLY)"


def test_text_columns_uppercased(c15):
    by = c15.set_index("project_name")
    assert by.loc["Annapurna", "utility"] == "PGAE"
    assert by.loc["Annapurna", "study_area"] == "PG&E FRESNO"
    assert by.loc["Annapurna", "state"] == "CA"


def test_provenance(c15):
    assert (c15.source_file == "cluster15.xlsx").all()
    assert (c15.source_run_date == "").all()       # the C15 file carries no run-date stamp
    assert {"pipeline_commit", "pipeline_run"} <= set(c15.columns)


@pytest.mark.real_data
def test_real_file_smoke(real_c15):
    assert_required_columns(real_c15, C15_REQUIRED)
    assert (real_c15.sheet_status == "ACTIVE").sum() > 50
    assert (real_c15.sheet_status == "WITHDRAWN").sum() > 0
    assert set(real_c15.deliverability) <= {"ENERGY ONLY (REQ)", "FULL CAPACITY (REQ)", ""}
    assert (real_c15.cluster == "C15").all()
    assert (real_c15.node_key != "").all()
    assert real_c15.net_mw.notna().all()
