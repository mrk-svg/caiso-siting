"""tpd.py: CAISO TPD allocation cycle results (2024 and 2025 layouts) and the per-node roll-up."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import pytest

from caiso_siting import nodes, tpd

TPD24_HEADER = ["PTO Area", "Q#\nWDAT#", "Allocation Group ",
                "Allocated Deliverability Status at Project Level", "Percent of Partial TPD Allocted "]
TPD24_ROWS = [
    ["SCE", 297, "A", "FCDSA", None],
    ["SDG&E", 1048, "A", "PCDSA", 0.663983903420523],
    ["PG&E", 1223, "B", "PCDSA", 0.6],
    ["PG&E", "WDT1532", "A", "FCDSA", None],          # distribution-level: not in the generator queue
    ["SCE", 3001, "A", "FCDSA", None],                # WITHDRAWN in the projects frame; must still count
    ["SCE", 999, "C", None, None],                    # no status at all
]
TPD25_TITLE = "2025 TPD Allocation Cycle Results by Request not Project"
TPD25_HEADER = ["PTO Area", "Q#\nWDAT#", "Allocation Group", "MW Requested for Allocation", "Allocation Percent"]
TPD25_ROWS = [
    ["DCRT", 1402, "A", 150, 0],                      # same project, two requests, both denied
    ["DCRT", 1402, "A", 180, 0],
    ["SCE", 297, "A", 200, 1.0],
    ["PG&E", 1223, "B", 100, 0.6],
    ["SDG&E", "2179-WD", "A", 50, 1.0],               # "-WD" id: outside the generator queue
    ["SCE", 1001, "A", 300, 1.0],
    ["SDG&E", 1048, "A", 90, None],                   # in the queue, but no percentage published
    ["SCE", "Unassigned#", "C", None, None],
]


def write_tpd_2024(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(TPD24_HEADER)
    for r in TPD24_ROWS:
        ws.append(r)
    wb.save(path)
    return path


def write_tpd_2025(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([TPD25_TITLE])
    ws.append(TPD25_HEADER)
    for r in TPD25_ROWS:
        ws.append(r)
    wb.save(path)
    return path


@pytest.fixture
def tpd_dir(tmp_path, monkeypatch) -> Path:
    write_tpd_2024(tmp_path / tpd.FILES[2024])
    write_tpd_2025(tmp_path / tpd.FILES[2025])
    monkeypatch.setattr(tpd, "DATA", tmp_path)
    return tmp_path


@pytest.fixture
def t24(tpd_dir) -> pd.DataFrame:
    return tpd.load_year(2024, tpd_dir / tpd.FILES[2024]).set_index("queue_id")


@pytest.fixture
def t25(tpd_dir) -> pd.DataFrame:
    return tpd.load_year(2025, tpd_dir / tpd.FILES[2025])


# ---------------------------------------------------------------- header detection

def test_find_header_rows(tpd_dir):
    assert tpd._find_header(tpd_dir / tpd.FILES[2024]) == 0       # header is row 1
    assert tpd._find_header(tpd_dir / tpd.FILES[2025]) == 1       # title row above the header


def test_columns_and_dtypes(t24, t25):
    expected = {"tpd_year", "pto", "queue_id", "allocation_group", "status", "allocation_pct",
                "mw_requested", "mw_allocated", "in_generator_queue", "source_file", "pipeline_commit"}
    assert expected <= set(t25.columns) and expected <= set(t24.reset_index().columns)
    assert (t25.tpd_year == 2025).all() and (t24.tpd_year == 2024).all()
    assert (t25.source_file == "tpd_2025.xlsx").all()
    assert pd.api.types.is_numeric_dtype(t25.mw_requested)
    assert pd.api.types.is_numeric_dtype(t25.allocation_pct)


# ------------------------------------------------------------------- 2024 layout

def test_2024_pto_normalisation_and_groups(t24):
    assert t24.loc["1048", "pto"] == "SDGE" and t24.loc["1223", "pto"] == "PGAE" and t24.loc["297", "pto"] == "SCE"
    assert t24.loc["1223", "allocation_group"] == "B"
    assert set(t24.pto) == {"SCE", "SDGE", "PGAE"}


def test_2024_status_and_allocation_pct(t24):
    assert t24.loc["297", "status"] == "FCDSA" and t24.loc["297", "allocation_pct"] == 1.0
    assert t24.loc["1048", "status"] == "PCDSA"
    assert t24.loc["1048", "allocation_pct"] == pytest.approx(0.663983903420523)
    assert t24.loc["1223", "allocation_pct"] == 0.6
    assert t24.loc["999", "status"] == "" and pd.isna(t24.loc["999", "allocation_pct"])
    assert t24.mw_requested.isna().all() and t24.mw_allocated.isna().all()   # the 2024 file carries no MW


def test_2024_generator_queue_flag(t24):
    assert t24.in_generator_queue.to_dict() == {"297": True, "1048": True, "1223": True, "WDT1532": False,
                                                "3001": True, "999": True}


# ------------------------------------------------------------------- 2025 layout

def test_2025_status_from_allocation_percent(t25):
    by = t25.set_index(["queue_id", "mw_requested"])
    assert by.loc[("297", 200.0), "status"] == "FCDSA"         # 1.0
    assert by.loc[("1223", 100.0), "status"] == "PCDSA"        # 0 < pct < 1
    assert by.loc[("1402", 150.0), "status"] == "NONE"         # 0
    assert by.loc[("1402", 180.0), "status"] == "NONE"
    assert t25.set_index("queue_id").loc["Unassigned#", "status"] == ""   # blank percent


def test_2025_mw_allocated(t25):
    by = t25.set_index(["queue_id", "mw_requested"])
    assert by.loc[("297", 200.0), "mw_allocated"] == 200.0
    assert by.loc[("1223", 100.0), "mw_allocated"] == 60.0
    assert by.loc[("1402", 150.0), "mw_allocated"] == 0.0
    assert by.loc[("2179-WD", 50.0), "mw_allocated"] == 50.0
    assert pd.isna(t25.set_index("queue_id").loc["Unassigned#", "mw_allocated"])


def test_2025_pto_and_generator_queue_flag(t25):
    by = t25.drop_duplicates("queue_id").set_index("queue_id")
    assert by.loc["1223", "pto"] == "PGAE" and by.loc["2179-WD", "pto"] == "SDGE"
    assert by.loc["2179-WD", "in_generator_queue"] is np.False_ or not by.loc["2179-WD", "in_generator_queue"]
    assert not by.loc["Unassigned#", "in_generator_queue"]
    assert by.loc["1402", "in_generator_queue"] and by.loc["297", "in_generator_queue"]
    assert (t25.queue_id != "").all()


# --------------------------------------------------------------------- load_all

def test_load_all_concatenates_both_years(tpd_dir):
    t = tpd.load_all()
    assert t.tpd_year.value_counts().to_dict() == {2025: 8, 2024: 6}
    assert list(t.index) == list(range(14))


def test_load_all_skips_missing_years(tpd_dir):
    (tpd_dir / tpd.FILES[2024]).unlink()
    t = tpd.load_all()
    assert set(t.tpd_year) == {2025}


def test_load_all_without_files_is_empty_with_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(tpd, "DATA", tmp_path)
    t = tpd.load_all()
    assert t.empty
    assert {"tpd_year", "queue_id", "status", "mw_requested", "mw_allocated", "in_generator_queue"} <= set(t.columns)


# --------------------------------------------------------------------- per_node

PROJECTS = pd.DataFrame({
    "queue_position": ["297", "1001", "1402", "1223", "1048", "3001", "999", None, "297"],
    "node_key": ["WHIRLWIND", "WHIRLWIND", "VINCENT", "VACA DIXON", "OTAY MESA", "WHIRLWIND", "NOWHERE",
                 "FOOTER", "WHIRLWIND"],
    "sheet_status": ["ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "WITHDRAWN", "ACTIVE", "ACTIVE", "ACTIVE"],
})


def test_per_node_rollup(tpd_dir):
    pn = tpd.per_node(tpd.load_all(), PROJECTS)
    assert pn.index.name == "node_key"
    assert list(pn.columns) == nodes.TPD_COLS
    w = pn.loc["WHIRLWIND"]
    assert w.tpd25_projects == 2 and w.tpd25_req_mw == 500 and w.tpd25_alloc_mw == 500 and w.tpd25_denied_mw == 0
    assert w.tpd24_fcdsa_projects == 2            # 297 (ACTIVE) + 3001 (WITHDRAWN in projects)
    assert w.tpd24_pcdsa_projects == 0
    v = pn.loc["VINCENT"]
    assert v.tpd25_projects == 1                  # two requests, one project
    assert v.tpd25_req_mw == 330 and v.tpd25_alloc_mw == 0 and v.tpd25_denied_mw == 330
    assert v.tpd24_fcdsa_projects == 0 and v.tpd24_pcdsa_projects == 0
    vd = pn.loc["VACA DIXON"]
    assert vd.tpd25_req_mw == 100 and vd.tpd25_alloc_mw == 60 and vd.tpd25_denied_mw == 0
    assert vd.tpd24_pcdsa_projects == 1
    o = pn.loc["OTAY MESA"]
    assert o.tpd25_projects == 1 and o.tpd25_req_mw == 90 and o.tpd24_pcdsa_projects == 1
    assert (pn.loc["NOWHERE"] == 0).all()         # blank 2024 status counts as nothing
    assert "FOOTER" not in pn.index               # NaN queue_position dropped
    assert pn.notna().all().all()
    assert (pn.tpd25_alloc_mw <= pn.tpd25_req_mw).all() and (pn.tpd25_denied_mw <= pn.tpd25_req_mw).all()


def test_per_node_unallocated_is_refusals_plus_partial_remainder(tpd_dir):
    """"Denied" alone understates what a developer did not get: a 60 % allocation leaves 40 % behind."""
    pn = tpd.per_node(tpd.load_all(), PROJECTS)
    vd = pn.loc["VACA DIXON"]                     # one 100 MW request allocated at 60 %
    assert (vd.tpd25_req_mw, vd.tpd25_alloc_mw) == (100, 60)
    assert vd.tpd25_denied_mw == 0                # nothing was refused outright
    assert vd.tpd25_unalloc_mw == 40              # but 40 MW was not allocated
    v = pn.loc["VINCENT"]                         # two requests, both at 0 %
    assert v.tpd25_denied_mw == 330 and v.tpd25_unalloc_mw == 330
    w = pn.loc["WHIRLWIND"]                       # everything allocated in full
    assert w.tpd25_alloc_mw == 500 and w.tpd25_unalloc_mw == 0
    # unalloc is exactly requested - allocated, everywhere
    assert (pn.tpd25_unalloc_mw == (pn.tpd25_req_mw - pn.tpd25_alloc_mw).round(1)).all()
    assert (pn.tpd25_denied_mw <= pn.tpd25_unalloc_mw + 1e-9).all()


def test_per_node_missing_percentage_is_unknown_not_denied(tpd_dir):
    """A NaN allocation percentage is missing data. Reporting it as a refusal would invent a
    decision CAISO never published."""
    pn = tpd.per_node(tpd.load_all(), PROJECTS)
    o = pn.loc["OTAY MESA"]                       # queue 1048: 90 MW requested, percentage blank
    assert o.tpd25_req_mw == 90
    assert o.tpd25_unknown_mw == 90
    assert o.tpd25_denied_mw == 0                 # NOT counted as a refusal
    assert o.tpd25_alloc_mw == 0                  # NaN * MW contributes nothing
    assert o.tpd25_unalloc_mw == 90               # still "did not get it"
    # nodes with a published percentage carry no unknown MW
    assert pn.loc["WHIRLWIND", "tpd25_unknown_mw"] == 0
    assert pn.loc["VINCENT", "tpd25_unknown_mw"] == 0
    assert (pn.tpd25_denied_mw + pn.tpd25_unknown_mw <= pn.tpd25_req_mw + 1e-9).all()


def test_tpd_cols_lists_every_per_node_column(tpd_dir):
    pn = tpd.per_node(tpd.load_all(), PROJECTS)
    assert list(pn.columns) == nodes.TPD_COLS
    assert "tpd25_unalloc_mw" in nodes.TPD_COLS and "tpd25_unknown_mw" in nodes.TPD_COLS


def test_per_node_splits_requests_and_refusals_by_allocation_group(tpd_dir):
    """A 0 % on a group-A (executed PPA) request is a different fact from a 0 % on group D (no PPA)."""
    pn = tpd.per_node(tpd.load_all(), PROJECTS)
    v = pn.loc["VINCENT"]                         # 1402: two group-A requests, both at 0 %
    assert v.tpd25_req_A_mw == 330 and v.tpd25_denied_A_mw == 330 and v.tpd25_denied_ppa_mw == 330
    assert v.tpd25_req_B_mw == 0 and v.tpd25_denied_D_mw == 0
    vd = pn.loc["VACA DIXON"]                     # 1223: group B, 60 % — not a refusal
    assert vd.tpd25_req_B_mw == 100 and vd.tpd25_denied_B_mw == 0 and vd.tpd25_denied_ppa_mw == 0
    w = pn.loc["WHIRLWIND"]                       # 297 + 1001: group A, fully allocated
    assert w.tpd25_req_A_mw == 500 and w.tpd25_denied_A_mw == 0
    for g in tpd.GROUP_ORDER:                     # group columns partition the totals
        assert (pn[f"tpd25_denied_{g}_mw"] <= pn[f"tpd25_req_{g}_mw"]).all()
    assert (pn[[f"tpd25_req_{g}_mw" for g in tpd.GROUP_ORDER]].sum(axis=1) == pn.tpd25_req_mw).all()
    assert (pn[[f"tpd25_denied_{g}_mw" for g in tpd.GROUP_ORDER]].sum(axis=1) == pn.tpd25_denied_mw).all()
    assert set(tpd.GROUPS) == {"A", "B", "C", "D"}


def test_node_rows_one_row_per_request_with_group_and_name(tpd_dir):
    projects = PROJECTS.assign(project_name=["P297", "P1001", "P1402", "P1223", "P1048", "P3001", "P999", "F", "P297"])
    rows = tpd.node_rows(tpd.load_all(), projects)
    v = rows[rows.node_key == "VINCENT"]
    assert len(v) == 2 and set(v.allocation_group) == {"A"} and set(v.project_name) == {"P1402"}
    assert (v.allocation_pct == 0).all() and v.mw_requested.sum() == 330
    assert "2179-WD" not in set(rows.queue_id) and "WDT1532" not in set(rows.queue_id)
    assert set(rows.columns) >= {"node_key", "tpd_year", "queue_id", "project_name", "allocation_group",
                                 "mw_requested", "allocation_pct", "mw_allocated", "status"}
    # tolerant of a projects frame without names (old snapshots)
    assert (tpd.node_rows(tpd.load_all(), PROJECTS).project_name == "").all()
    assert tpd.node_rows(tpd.load_all().iloc[0:0], PROJECTS).empty


def test_per_node_ignores_non_queue_ids(tpd_dir):
    projects = pd.DataFrame({"queue_position": ["WDT1532", "2179-WD"], "node_key": ["X", "Y"]})
    pn = tpd.per_node(tpd.load_all(), projects)
    assert pn.empty


def test_per_node_strips_queue_position_whitespace(tpd_dir):
    projects = pd.DataFrame({"queue_position": [" 297 "], "node_key": ["W"]})
    pn = tpd.per_node(tpd.load_all(), projects)
    assert pn.loc["W", "tpd25_req_mw"] == 200 and pn.loc["W", "tpd24_fcdsa_projects"] == 1


# --------------------------------------------------------------- nodes.join_tpd

def test_join_tpd_adds_columns_and_fills_zero(tpd_dir, capsys):
    n = pd.DataFrame({"node_key": ["WHIRLWIND", "VINCENT", "ELSEWHERE"], "pipeline_mw": [1.0, 2.0, 3.0]})
    out = nodes.join_tpd(n, PROJECTS)
    assert set(nodes.TPD_COLS) <= set(out.columns)
    by = out.set_index("node_key")
    assert by.loc["WHIRLWIND", "tpd25_alloc_mw"] == 500 and by.loc["VINCENT", "tpd25_denied_mw"] == 330
    assert by.loc["VINCENT", "tpd25_unalloc_mw"] == 330
    assert (by.loc["ELSEWHERE", nodes.TPD_COLS] == 0).all()
    assert out.pipeline_mw.tolist() == [1.0, 2.0, 3.0]            # row order preserved
    assert "2 nodes with 2025 TPD requests" in capsys.readouterr().out


def test_join_tpd_without_files_zeroes_columns(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tpd, "DATA", tmp_path)
    out = nodes.join_tpd(pd.DataFrame({"node_key": ["A"]}), PROJECTS)
    assert (out[nodes.TPD_COLS] == 0).all().all()
    assert "TPD columns are zero" in capsys.readouterr().out


# ------------------------------------------------------------------ real files

@pytest.fixture(scope="session")
def real_tpd() -> pd.DataFrame:
    for f in tpd.FILES.values():
        if not (tpd.DATA / f).exists():
            pytest.skip(f"real data file missing: {tpd.DATA / f}")
    return tpd.load_all()


@pytest.mark.real_data
def test_real_files_load(real_tpd):
    t = real_tpd
    assert set(t.tpd_year) == {2024, 2025}
    assert (t.tpd_year == 2025).sum() > 150
    assert set(t.pto) <= {"SCE", "SDGE", "PGAE", "DCRT", "GLW", "SZT", "VEA"}
    assert (t.queue_id != "").all()
    assert set(t[t.tpd_year == 2024].status) <= {"FCDSA", "PCDSA", ""}
    assert set(t[t.tpd_year == 2025].status) <= {"FCDSA", "PCDSA", "NONE", ""}
    t25 = t[t.tpd_year == 2025]
    assert t25.allocation_pct.between(0, 1).all()
    assert (t25.mw_allocated <= t25.mw_requested + 0.051).all()   # mw_allocated is rounded to 0.1
    assert (~t[t.queue_id.str.contains("WD|W\\d", regex=True)].in_generator_queue).all()
    assert t.in_generator_queue.mean() > 0.5


@pytest.mark.real_data
def test_real_per_node_with_public_report(real_tpd, real_pq):
    pn = tpd.per_node(real_tpd, real_pq)
    assert len(pn) > 50
    assert (pn.tpd25_alloc_mw <= pn.tpd25_req_mw + 1e-6).all()
    assert (pn.tpd25_denied_mw <= pn.tpd25_req_mw + 1e-6).all()
    assert (pn >= 0).all().all()
    assert pn.tpd25_req_mw.sum() > 0 and pn.tpd24_fcdsa_projects.sum() > 0
