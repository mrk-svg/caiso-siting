"""wdat.py: PG&E's Wholesale Distribution Access Tariff queue (title rows, numbered row, header on
row 4) and the per-substation roll-up."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from caiso_siting import nodes, wdat

D = dt.datetime

# Exact PG&E header row (verified against data/wdat_pge.xlsx posted 2026-08-27).
PGE_HEADER = [
    "Date Interconnection Request Received by PG&E", "Revised Queue Number (5/31/12)",
    "Interconnection Process Type Applied For", "Current Process Type", "Current Interconnection Request Status",
    "Customer Requested COD (from application)", "Updated Commercial Operation Date", "Actual In-Service Date",
    "Facility County", "Substation", "Generation Type", "Summer Max Capacity (MW)",
    "Date Interconnection Request Deemed Complete", "Date Initial Review Provided to Applicant",
    "Initial Review Results (and Fail Reasons if Failed)", "Date Supplemental Review Provided To Applicant",
    "Supplemental Review Results (and Fail Reasons if Failed)", "Electrical Independence Test Results",
    "Date System Impact Study / Phase 1 Provided To Applicant", "Date Facilities Study / Phase 2 Provided To Applicant",
    "Interconnection Agreement Status", "Notes",
]
STUDY_FILLER = ["N/A"] * 8   # the eight study-tracking columns the parser does not map


def pge_row(received, qn, process, status, cod, updated_cod, actual, county, sub, gen, mw, ia, note="") -> list:
    return [received, qn, process, process, status, cod, updated_cod, actual, county, sub, gen, mw,
            *STUDY_FILLER, ia, note]


PGE_ROWS = [
    pge_row(D(2006, 2, 23), "0001-WD", "Independent Study", "In Service", "Not Provided", D(2009, 6, 18), D(2009, 5, 6),
            "CONTRA COSTA", "WILLOW PASS SUB", "Engine", 3.852, "Executed", "No former queue position"),
    pge_row(D(2006, 9, 22), "0002-WD", "Fast Track", "Withdrawn", "1/1/2008", "Withdrawn", "Withdrawn",
            "Withdrawn", "Withdrawn", "Other", 1, "Withdrawn"),                        # Substation 'Withdrawn': dropped
    pge_row(D(2020, 3, 30), "0003-WD", "Fast Track", "Active", "12/31/2027", None, None,
            "Kern County", "WHIRLWIND SUB", "Solar PV", 20, "Pending"),
    pge_row(D(2021, 5, 1), "0004-WD", "Cluster", "Active", D(2028, 6, 1), D(2028, 12, 1), None,
            "KERN", "Whirlwind Sub", "Storage", 10, "Pending"),
    pge_row(D(2022, 1, 15), "0005-WD", "Detailed Study", "Active", D(2027, 1, 1), None, None,
            "FRESNO", "HERNDON SUB", "Solar PV, Storage", 8, "Pending"),
    pge_row(D(2019, 7, 4), "0006-WD", "Fast Track", "withdrawn", D(2021, 1, 1), None, None,
            "FRESNO", "HERNDON SUB", "Battery", 5, "None"),                             # lower-case status
    pge_row(D(2023, 2, 2), "0007-WD", "DGSP", "Active", D(2027, 1, 1), None, None,
            "SAN BERNADINO", "LUGO", "Solar PV", 2.5, "Pending"),
    pge_row(D(2023, 3, 3), None, "Fast Track", "Active", D(2027, 1, 1), None, None,
            "KERN", "SOMEWHERE SUB", "Solar PV", 1, "Pending"),                         # blank queue number: dropped
    pge_row(D(2024, 4, 4), "0008-WD", "Cluster", "Under Review", D(2029, 1, 1), None, None,
            "ALAMEDA", "TESLA SUB", "Storage", 4, "None"),                              # unmapped status -> ""
    pge_row(D(2015, 5, 5), "0009-WD", "Fast Track", "In Service", D(2016, 1, 1), D(2016, 1, 1), D(2016, 2, 1),
            "CONTRA COSTA", "WILLOW PASS SUB", "Storage", 2, "Executed"),
]


def write_wdat_pge(path: Path, header: list[str] | None = None, rows: list[list] | None = None) -> Path:
    header = header or PGE_HEADER
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Public Queue"
    ws.append(["PG&E Wholesale Distribution Queue Posted:", None, None, D(2026, 8, 27)])
    ws.append(["Interconnection Requests Received Through:", None, None, D(2026, 7, 31)])
    ws.append(list(range(1, len(header) + 1)))
    ws.append(header)
    for r in rows if rows is not None else PGE_ROWS:
        assert len(r) == len(header), (len(r), len(header))
        ws.append(r)
    wb.save(path)
    return path


@pytest.fixture
def wdat_dir(tmp_path, monkeypatch) -> Path:
    write_wdat_pge(tmp_path / wdat.FILES["PGAE"])
    monkeypatch.setattr(wdat, "DATA", tmp_path)
    return tmp_path


@pytest.fixture
def w(wdat_dir) -> pd.DataFrame:
    return wdat.load_utility("PGAE", wdat_dir / wdat.FILES["PGAE"])


# ----------------------------------------------------------------- header detection

def test_find_header_is_row_4(wdat_dir):
    assert wdat._find_header(wdat_dir / wdat.FILES["PGAE"]) == 3


def test_find_header_raises_without_header(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    for i in range(10):
        ws.append([f"row {i}", "nothing to see", "Queue only, no station column"])
    p = tmp_path / "nohdr.xlsx"
    wb.save(p)
    with pytest.raises(ValueError, match="no header row with 'Substation' and 'Queue'"):
        wdat._find_header(p)


def test_load_utility_skips_unmapped_utility(tmp_path, capsys):
    out = wdat.load_utility("SCE", tmp_path / "wdat_sce.xlsx")
    assert out.empty and isinstance(out, pd.DataFrame)
    assert "no column map for SCE" in capsys.readouterr().out


def test_load_utility_reports_unmapped_columns(tmp_path, capsys):
    header = [h if h != "Notes" else "Remarks" for h in PGE_HEADER]
    df = wdat.load_utility("PGAE", write_wdat_pge(tmp_path / "x.xlsx", header=header))
    assert "unmapped canonical columns ['notes']" in capsys.readouterr().out
    assert (df.notes == "").all()
    assert len(df) == 8


# --------------------------------------------------------------------- parsing

def test_row_filtering(w):
    assert w.queue_position.tolist() == ["0001-WD", "0003-WD", "0004-WD", "0005-WD", "0006-WD", "0007-WD",
                                         "0008-WD", "0009-WD"]
    assert "SOMEWHERE" not in set(w.node_key)          # blank queue number
    assert not w.poi.isin(["WITHDRAWN", ""]).any()     # substation 'Withdrawn'


def test_sheet_status_mapping(w):
    by = w.set_index("queue_position")
    assert by.loc["0001-WD", "sheet_status"] == "COMPLETED"        # In Service
    assert by.loc["0003-WD", "sheet_status"] == "ACTIVE"
    assert by.loc["0006-WD", "sheet_status"] == "WITHDRAWN"        # lower-case 'withdrawn'
    assert by.loc["0006-WD", "status_raw"] == "withdrawn"
    assert by.loc["0008-WD", "sheet_status"] == ""                 # 'Under Review' is not mapped
    assert set(w.sheet_status) == {"ACTIVE", "COMPLETED", "WITHDRAWN", ""}


def test_storage_mw_attribution(w):
    by = w.set_index("queue_position")
    assert by.loc["0004-WD", "storage_mw"] == 10.0                 # storage-only: full MW
    assert by.loc["0004-WD", "is_standalone_storage"]
    assert by.loc["0005-WD", "storage_mw"] == 4.0                  # solar + storage: half
    assert by.loc["0005-WD", "has_storage"] and by.loc["0005-WD", "has_solar"]
    assert not by.loc["0005-WD", "is_standalone_storage"]
    assert by.loc["0003-WD", "storage_mw"] == 0.0                  # solar-only
    assert by.loc["0006-WD", "storage_mw"] == 5.0                  # 'Battery'
    assert by.loc["0001-WD", "storage_mw"] == 0.0                  # 'Engine'
    assert by.loc["0001-WD", "net_mw"] == pytest.approx(3.852)
    assert w.poi_mw.equals(w.net_mw)


def test_node_key_and_poi_base(w):
    by = w.set_index("queue_position")
    assert by.loc["0001-WD", "poi"] == "WILLOW PASS SUB"
    assert by.loc["0001-WD", "node_key"] == "WILLOW PASS"
    assert by.loc["0001-WD", "poi_base"] == "WILLOW PASS SUB"
    assert by.loc["0003-WD", "node_key"] == "WHIRLWIND" == by.loc["0004-WD", "node_key"]   # 'Whirlwind Sub' too
    assert by.loc["0007-WD", "node_key"] == "LUGO"


def test_county_cleanup(w):
    by = w.set_index("queue_position")
    assert by.loc["0003-WD", "county"] == "KERN"                   # 'Kern County'
    assert by.loc["0007-WD", "county"] == "SAN BERNARDINO"
    assert by.loc["0001-WD", "county"] == "CONTRA COSTA"


def test_dates_process_and_labels(w):
    by = w.set_index("queue_position")
    assert by.loc["0001-WD", "request_received"] == pd.Timestamp("2006-02-23")
    assert by.loc["0001-WD", "queue_year"] == 2006
    assert pd.isna(by.loc["0001-WD", "proposed_cod"])              # 'Not Provided'
    assert by.loc["0003-WD", "proposed_cod"] == pd.Timestamp("2027-12-31")   # '12/31/2027' string
    assert by.loc["0001-WD", "actual_cod"] == pd.Timestamp("2009-05-06")
    assert by.loc["0004-WD", "process"] == "Cluster"
    assert (w.utility == "PGAE").all() and (w.cluster == "WDAT-PGAE").all()
    assert by.loc["0007-WD", "ia_status"] == "Pending"


def test_provenance(w):
    assert (w.source_file == "wdat_pge.xlsx").all()
    assert {"source_run_date", "pipeline_commit", "pipeline_run"} <= set(w.columns)
    assert (w.source_run_date == "").all()


# --------------------------------------------------------------------- load_all

def test_load_all_reads_mapped_files_only(wdat_dir):
    (wdat_dir / wdat.FILES["SCE"]).write_bytes(b"")    # present but unmapped -> skipped, not an error
    out = wdat.load_all()
    assert len(out) == 8 and set(out.utility) == {"PGAE"}


def test_load_all_without_files_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(wdat, "DATA", tmp_path)
    assert wdat.load_all().empty


# --------------------------------------------------------------------- per_node

def test_per_node_aggregation(w):
    pn = wdat.per_node(w)
    assert list(pn.columns) == nodes.WDAT_COLS
    assert pn.index.name == "node_key"
    wh = pn.loc["WHIRLWIND"]
    assert wh.wdat_active_projects == 2 and wh.wdat_active_mw == 30 and wh.wdat_active_storage_mw == 10
    assert wh.wdat_inservice_mw == 0 and wh.wdat_withdrawn_mw == 0
    h = pn.loc["HERNDON"]
    assert h.wdat_active_projects == 1 and h.wdat_active_mw == 8 and h.wdat_active_storage_mw == 4
    assert h.wdat_withdrawn_mw == 5
    wp = pn.loc["WILLOW PASS"]
    assert wp.wdat_active_projects == 0 and wp.wdat_inservice_mw == 5.9     # 3.852 + 2, rounded
    assert pn.loc["LUGO", "wdat_active_mw"] == 2.5
    assert "TESLA" not in pn.index                                          # unmapped status counts nowhere
    assert pn.notna().all().all() and (pn >= 0).all().all()


def test_per_node_empty_frame_schema():
    pn = wdat.per_node(pd.DataFrame())
    assert pn.empty and list(pn.columns) == nodes.WDAT_COLS


# ---------------------------------------------------------------- nodes.join_wdat

def test_join_wdat_synthetic(wdat_dir, capsys):
    n = pd.DataFrame({"node_key": ["WHIRLWIND", "HERNDON", "VINCENT"], "pipeline_mw": [1.0, 2.0, 3.0]})
    out = nodes.join_wdat(n)
    by = out.set_index("node_key")
    assert by.loc["WHIRLWIND", "wdat_active_mw"] == 30 and by.loc["HERNDON", "wdat_withdrawn_mw"] == 5
    assert (by.loc["VINCENT", nodes.WDAT_COLS] == 0).all()
    assert out.pipeline_mw.tolist() == [1.0, 2.0, 3.0]
    msg = capsys.readouterr().out
    assert "2 CAISO nodes also carry active WDAT requests (38 MW)" in msg
    assert "2 WDAT-only substations" in msg                                 # WILLOW PASS, LUGO


def test_join_wdat_without_files_zeroes_columns(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wdat, "DATA", tmp_path)
    out = nodes.join_wdat(pd.DataFrame({"node_key": ["A", "B"]}))
    assert list(out.columns) == ["node_key", *nodes.WDAT_COLS]
    assert (out[nodes.WDAT_COLS] == 0).all().all()
    assert "WDAT columns are zero" in capsys.readouterr().out


# ------------------------------------------------------------------- real file

@pytest.fixture(scope="session")
def real_wdat() -> pd.DataFrame:
    if not (wdat.DATA / wdat.FILES["PGAE"]).exists():
        pytest.skip("real data file missing: wdat_pge.xlsx")
    return wdat.load_all()


@pytest.mark.real_data
def test_real_file_smoke(real_wdat):
    w = real_wdat
    assert len(w) > 4000
    assert set(w.sheet_status) == {"ACTIVE", "COMPLETED", "WITHDRAWN"}
    assert (w.utility == "PGAE").all()
    assert w.queue_position.str.fullmatch(r"\d{4}-(WD|RD)").all()   # "-RD" suffix appears on recent rows
    assert (w.node_key != "").all() and not w.poi.isin(["WITHDRAWN", "N/A", "TBD"]).any()
    assert w.net_mw.notna().mean() > 0.95
    assert (w.storage_mw <= w.net_mw.fillna(0) + 1e-9).all()
    assert (w.node_key == "WILLOW PASS").any()


@pytest.mark.real_data
def test_real_per_node(real_wdat):
    pn = wdat.per_node(real_wdat)
    assert len(pn) > 500
    assert (pn >= 0).all().all() and pn.notna().all().all()
    assert (pn.wdat_active_storage_mw <= pn.wdat_active_mw + 1e-6).all()
    assert (pn.wdat_active_projects > 0).sum() > 200
