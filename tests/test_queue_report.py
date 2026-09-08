"""queue_report.py against a synthetic workbook that mirrors CAISO's public queue layout,
plus smoke tests on the real file."""
from __future__ import annotations

import re

import pandas as pd
import pytest
from conftest import assert_required_columns, missing_required, write_queue_xlsx

from caiso_siting import queue_report
from caiso_siting.config import xlsx_run_date


@pytest.fixture
def pq(queue_xlsx) -> pd.DataFrame:
    return queue_report.load_all(queue_xlsx)


# ------------------------------------------------------------------ layout facts

def test_layout_constants_match_caiso():
    assert queue_report.HEADER_ROW == 3   # Excel row 4
    assert list(queue_report.SHEETS) == ["Grid GenerationQueue", "Completed Generation Projects",
                                         "Withdrawn Generation Projects"]
    assert set(queue_report.SHEETS.values()) == {"ACTIVE", "COMPLETED", "WITHDRAWN"}
    assert queue_report.RENAME["Project Name - Confidential"] == "project_name"


def test_load_sheet_collapses_newlines_in_headers(queue_xlsx):
    df = queue_report.load_sheet(queue_xlsx, "Grid GenerationQueue", "ACTIVE")
    # "Study\nProcess", "Current\nOn-line Date", "Interconnection Agreement \nStatus" all map
    assert {"study_process", "current_cod", "ia_status", "study_fas_phase2"} <= set(df.columns)
    assert not any(c.startswith("_drop_") or c.startswith("Unnamed") for c in df.columns)
    assert df["sheet_status"].eq("ACTIVE").all()
    assert len(df) == 3


def test_load_sheet_withdrawn_sheet_uses_confidential_name_header(queue_xlsx):
    df = queue_report.load_sheet(queue_xlsx, "Withdrawn Generation Projects", "WITHDRAWN")
    assert "project_name" in df.columns
    assert {"withdrawn_date", "withdrawal_reason"} <= set(df.columns)
    assert df.project_name.tolist() == ["DEAD WIND", "DEAD SOLAR"]


# ------------------------------------------------------------------- canonical

def test_load_all_has_every_required_canonical_column(pq):
    assert_required_columns(pq)
    assert missing_required(pq) == []


def test_load_all_row_counts_and_sheet_status(pq):
    assert pq.sheet_status.value_counts().to_dict() == {"ACTIVE": 3, "COMPLETED": 1, "WITHDRAWN": 2}
    assert pq.status.tolist() == ["ACTIVE"] * 3 + ["COMPLETED"] + ["WITHDRAWN"] * 2


def test_numeric_coercion(pq):
    by = pq.set_index("project_name")
    assert pd.api.types.is_numeric_dtype(pq.net_mw)
    assert pd.api.types.is_numeric_dtype(pq.mw_1)
    assert pd.api.types.is_float_dtype(pq.tpd_pct)
    assert by.loc["STANDALONE BESS", "net_mw"] == 1250.0       # "1,250" -> 1250
    assert by.loc["STANDALONE BESS", "mw_1"] == 1250.0
    assert by.loc["HYBRID ONE", "net_mw"] == 200.0
    assert by.loc["HYBRID ONE", "tpd_pct"] == 100.0
    assert pd.isna(by.loc["STANDALONE BESS", "tpd_pct"])
    assert pd.isna(by.loc["GAS PEAKER", "mw_2"])


def test_date_coercion(pq):
    by = pq.set_index("project_name")
    for c in ("queue_date", "current_cod", "withdrawn_date", "request_received", "proposed_cod"):
        assert pd.api.types.is_datetime64_any_dtype(pq[c]), c
    assert by.loc["HYBRID ONE", "queue_date"] == pd.Timestamp("2021-04-15 07:00")
    assert by.loc["HYBRID ONE", "queue_year"] == 2021
    assert by.loc["DEAD WIND", "withdrawn_year"] == 2024
    assert pd.isna(by.loc["HYBRID ONE", "withdrawn_date"])
    assert pd.isna(by.loc["HYBRID ONE", "withdrawn_year"])


def test_queue_position_kept_as_string(pq):
    # CAISO mixes ints and "1003A"-style positions; the join key must stay text
    assert set(pq.queue_position) == {"1001", "1002", "1003A", "2001", "3001", "3002"}


def test_storage_flags_and_storage_mw(pq):
    by = pq.set_index("project_name")
    assert by.loc["HYBRID ONE", "has_storage"] and by.loc["HYBRID ONE", "has_solar"]
    assert not by.loc["HYBRID ONE", "is_standalone_storage"]
    assert by.loc["HYBRID ONE", "storage_mw"] == 150.0          # only MW-2 (Type-2 = Storage)
    assert by.loc["STANDALONE BESS", "is_standalone_storage"]
    assert by.loc["STANDALONE BESS", "storage_mw"] == 1250.0
    assert not by.loc["GAS PEAKER", "has_storage"]
    assert by.loc["GAS PEAKER", "storage_mw"] == 0.0
    assert by.loc["DEAD WIND", "has_wind"] and by.loc["DEAD WIND", "storage_mw"] == 60.0


def test_poi_mw_equals_net_mw(pq):
    assert pq.poi_mw.equals(pq.net_mw)


def test_withdrew_post_phase2_flag(pq):
    by = pq.set_index("project_name")
    assert by.loc["DEAD WIND", "withdrew_post_phase2"]         # WITHDRAWN + Phase II 'Complete'
    assert not by.loc["DEAD SOLAR", "withdrew_post_phase2"]    # WITHDRAWN + Phase II 'In Progress'
    assert not by.loc["HYBRID ONE", "withdrew_post_phase2"]    # ACTIVE with Phase II 'Complete'
    assert not by.loc["OPERATING SOLAR", "withdrew_post_phase2"]


def test_county_cleanup_applied(pq):
    by = pq.set_index("project_name")
    assert by.loc["HYBRID ONE", "county"] == "KERN"
    assert by.loc["STANDALONE BESS", "county"] == "FRESNO/MERCED"
    assert by.loc["GAS PEAKER", "county"] == "LOS ANGELES"
    assert by.loc["OPERATING SOLAR", "county"] == "FRESNO/KINGS"
    assert by.loc["DEAD WIND", "county"] == "SAN BERNARDINO"
    assert by.loc["DEAD SOLAR", "county"] == "MOHAVE"


def test_text_columns_uppercased_and_cluster_label(pq):
    by = pq.set_index("project_name")
    assert by.loc["HYBRID ONE", "poi"] == "WHIRLWIND SUBSTATION 230 KV"
    assert by.loc["HYBRID ONE", "deliverability"] == "FULL CAPACITY"
    assert by.loc["HYBRID ONE", "tpd_group"] == "GROUP A"
    assert by.loc["HYBRID ONE", "cluster"] == "CLUSTER 14"
    assert by.loc["GAS PEAKER", "cluster"] == "SERIAL LGIP"          # no cluster number -> study process
    assert by.loc["STANDALONE BESS", "tpd_group"] == ""              # blank stays "", not NaN


def test_node_key_and_poi_base(pq):
    by = pq.set_index("project_name")
    assert by.loc["HYBRID ONE", "node_key"] == "WHIRLWIND"
    assert by.loc["HYBRID ONE", "poi_base"] == "WHIRLWIND SUBSTATION"
    assert by.loc["STANDALONE BESS", "node_key"] == "VACA DIXON"
    assert by.loc["DEAD SOLAR", "node_key"] == "NORTH GILA HOODOO WASH"
    assert by.loc["DEAD SOLAR", "poi_base"] == "NORTH GILA - HOODOO WASH"
    # the same substation on three sheets shares one key: that is what nodes.py joins on
    assert (pq.node_key == "WHIRLWIND").sum() == 3


def test_provenance_columns(pq, queue_xlsx):
    for c in ("source_file", "source_run_date", "pipeline_commit", "pipeline_run"):
        assert c in pq.columns and pq[c].nunique() == 1, c
    assert pq.source_file.iloc[0] == "publicqueuereport.xlsx"
    assert pq.source_run_date.iloc[0] == "2026-09-07"
    assert xlsx_run_date(queue_xlsx) == "2026-09-07"
    assert isinstance(pq.pipeline_commit.iloc[0], str) and pq.pipeline_commit.iloc[0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", pq.pipeline_run.iloc[0])


def test_missing_run_date_stamp_gives_empty_provenance(tmp_path):
    path = write_queue_xlsx(tmp_path / "nostamp.xlsx", run_date=None)
    assert xlsx_run_date(path) is None
    df = queue_report.load_all(path)
    assert (df.source_run_date == "").all()


# ------------------------------------------------------------ header-drift guard

def test_header_drift_is_caught_by_required_column_guard(tmp_path):
    """If CAISO renames a header the parser does not recognise, the canonical column must be
    ABSENT (not silently mis-mapped), and the guard must name it."""
    drifted = write_queue_xlsx(tmp_path / "drift.xlsx", header_overrides={
        "Interconnection Agreement \nStatus": "IA Stage",        # -> ia_status vanishes
        "TPD Allocation Group": "Allocation Bucket",              # -> tpd_group vanishes
    })
    df = queue_report.load_all(drifted)
    assert "ia_status" not in df.columns
    assert "tpd_group" not in df.columns
    assert {"ia_stage", "allocation_bucket"} <= set(df.columns)   # auto-snake_cased instead
    assert missing_required(df) == ["tpd_group", "ia_status"]
    with pytest.raises(AssertionError, match=r"missing.*\['tpd_group', 'ia_status'\]"):
        assert_required_columns(df)


def test_minor_header_wording_drift_still_maps_by_prefix(tmp_path):
    # the parser prefix-matches the first 20 chars, so appended wording keeps the mapping
    drifted = write_queue_xlsx(tmp_path / "prefix.xlsx", header_overrides={
        "Interconnection Agreement \nStatus": "Interconnection Agreement Status (as of run date)",
        "Station or Transmission Line": "Station or Transmission Line / POI",
    })
    df = queue_report.load_all(drifted)
    assert_required_columns(df)
    assert df.set_index("project_name").loc["HYBRID ONE", "ia_status"] == "Executed"


def test_footer_disclaimer_row_is_dropped(tmp_path):
    """CAISO appends a disclaimer paragraph under each sheet. It has no queue position and
    must not survive as a project row."""
    path = write_queue_xlsx(tmp_path / "footer.xlsx", footer=True)
    df = queue_report.load_all(path)
    footer_rows = df[df.project_name.str.startswith("The contents of these pages")]
    assert footer_rows.empty, (
        f"{len(footer_rows)} footer rows kept as projects (queue_position blank): "
        f"queue_report.load_sheet only drops rows whose project_name is NaN")


# ------------------------------------------------------------------- aggregates

def test_by_county(pq):
    out = queue_report.by_county(pq)
    assert out.loc["KERN", "active_mw"] == 200.0
    assert out.loc["KERN", "active_storage_mw"] == 150.0
    assert out.loc["SAN BERNARDINO", "withdrawn_projects"] == 1
    assert out.loc["SAN BERNARDINO", "withdrawal_rate_by_count"] == 1.0
    assert out.loc["FRESNO/KINGS", "completed_mw"] == 80.0
    assert out.loc["FRESNO/KINGS", "withdrawal_rate_by_mw"] == 0.0
    assert out.index[0] == "FRESNO/MERCED"           # sorted by active_mw desc (1250)


def test_by_poi_churn_ratio(pq):
    out = queue_report.by_poi(pq).set_index("poi_base")
    w = out.loc["WHIRLWIND SUBSTATION"]
    # groupby on (poi_base, county, utility): KERN/SCE active, SAN BERNARDINO/SCE withdrawn, FRESNO/KINGS completed
    assert len(w) == 3
    kern = out.reset_index().query("poi_base == 'WHIRLWIND SUBSTATION' and county == 'KERN'").iloc[0]
    assert kern.active_mw == 200.0 and kern.full_capacity_mw == 200.0 and kern.energy_only_mw == 0.0
    fm = out.reset_index().query("county == 'FRESNO/MERCED'").iloc[0]
    assert fm.energy_only_mw == 1250.0 and fm.full_capacity_mw == 0.0
    assert pd.isna(out.reset_index().query("county == 'SAN BERNARDINO'").iloc[0].churn_ratio)  # 0 surviving MW


def test_by_cluster_withdrawals_and_deliverability_pivots(pq):
    clus = queue_report.by_cluster(pq)
    assert clus.loc["CLUSTER 14", ("count", "ACTIVE")] == 2
    assert clus.loc["CLUSTER 14", ("sum", "ACTIVE")] == 1450
    wby = queue_report.withdrawals_by_year(pq)
    assert wby.loc[2024, "withdrawn_mw"] == 120 and wby.loc[2024, "withdrawn_storage_mw"] == 60
    assert wby.loc[2013, "withdrawn_projects"] == 1
    deliv = queue_report.deliverability(pq)
    assert deliv.loc["FULL CAPACITY", "GROUP A"] == 200
    assert deliv.loc["All", "All"] == 1500


# ------------------------------------------------------------- real-file smoke

@pytest.mark.real_data
def test_real_file_has_required_columns_and_active_rows(real_pq):
    assert_required_columns(real_pq)
    assert (real_pq.sheet_status == "ACTIVE").sum() > 200
    assert real_pq.source_run_date.iloc[0] == "2026-09-07"
    assert real_pq.net_mw.notna().mean() > 0.95
    assert (real_pq.node_key == "WHIRLWIND").any()


@pytest.mark.real_data
def test_real_file_blank_node_key_count(real_pq):
    blank = real_pq[real_pq.node_key == ""]
    assert len(blank) <= 2, blank[["project_name", "sheet_status", "queue_position"]].to_string()
