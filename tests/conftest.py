"""Shared fixtures: synthetic CAISO workbooks that reproduce the real layouts, plus
session-scoped loads of the real data files (loaded once so the suite stays fast)."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"

# Pin the package's root to this repo before caiso_siting.config resolves ROOT at import time,
# so the suite behaves the same from any working directory.
os.environ.setdefault("CAISO_SITING_ROOT", str(REPO_ROOT))

from caiso_siting import config  # noqa: E402

# Canonical columns the pipeline depends on downstream (nodes.py, diff.py, site).
# A CAISO header rename that drops any of these must fail loudly in the tests.
REQUIRED = [
    "project_name", "queue_position", "status", "study_process", "net_mw", "storage_mw",
    "county", "utility", "poi", "deliverability", "tpd_group", "ia_status", "current_cod",
    "withdrawn_date", "sheet_status", "node_key", "poi_base",
]


# Subset the Cluster 15 schema can supply (no application status, TPD group, IA status or
# current COD exist in that file; diff.load_pair fills those with NA).
C15_REQUIRED = [
    "project_name", "queue_position", "study_process", "net_mw", "storage_mw", "county", "utility",
    "poi", "deliverability", "withdrawn_date", "withdrawn_year", "withdrew_post_phase2", "sheet_status",
    "node_key", "poi_base", "cluster",
]


def missing_required(df: pd.DataFrame, required: list[str] = REQUIRED) -> list[str]:
    return [c for c in required if c not in df.columns]


def assert_required_columns(df: pd.DataFrame, required: list[str] = REQUIRED) -> None:
    """The header-drift guard. Fails with the list of canonical names that vanished."""
    missing = missing_required(df, required)
    assert set(required) <= set(df.columns), (
        f"canonical columns missing after load (CAISO header drift?): {missing}; "
        f"present: {sorted(df.columns)}"
    )


# --------------------------------------------------------------- public queue report

D = dt.datetime

# Exact header rows captured from publicqueuereport.xlsx (run date 09/07/2026), newlines included.
PQ_HEADER_ACTIVE = [
    "Project Name", "Queue Position", "Interconnection Request\nReceive Date", "Queue Date",
    "Application Status", "Study\nProcess", "Type-1", "Type-2", "Type-3", "Fuel-1", "Fuel-2", "Fuel-3",
    "MW-1", "MW-2", "MW-3", "Net MWs to Grid", "Full Capacity, Partial or Energy Only (FC/P/EO)",
    "TPD Allocation Percentage", "Off-Peak Deliverability and Economic Only", "TPD Allocation Group",
    "County", "State", "Utility", "PTO Study Region", "Station or Transmission Line",
    "Proposed\nOn-line Date\n(as filed with IR)", "Current\nOn-line Date", "Suspension Status",
    "Feasibility Study or Supplemental Review", "System Impact Study or \nPhase I Cluster Study",
    "Facilities Study (FAS) or \nPhase II Cluster Study", "Optional Study\n(OS)",
    "Interconnection Agreement \nStatus",
]
PQ_HEADER_COMPLETED = [
    "Project Name", "Queue Position", "Interconnection Request\nReceive Date", "Queue Date",
    "Application Status", "Study\nProcess", "Type-1", "Type-2", "Type-3", "Fuel-1", "Fuel-2", "Fuel-3",
    "MW-1", "MW-2", "MW-3", "Net MWs to Grid", "Full Capacity, Partial or Energy Only (FC/P/EO)",
    "TPD Allocation Percentage", "Off-Peak Deliverability and Economic Only", "TPD Allocation Group",
    "County", "State", "Utility", "PTO Study Region", "Station or Transmission Line",
    "Proposed\nOn-line Date\n(as filed with IR)", "Actual\nOn-line Date",
    "Feasibility Study or Supplemental Review", "System Impact Study or \nPhase I Cluster Study",
    "Facilities Study (FAS) or \nPhase II Cluster Study", "Optional Study\n(OS)",
    "Interconnection Agreement \nStatus",
]
PQ_HEADER_WITHDRAWN = [
    "Project Name - Confidential", "Queue Position", "Interconnection Request\nReceive Date", "Queue Date",
    "Application Status", "Withdrawn Date", "Study\nProcess", "Type-1", "Type-2", "Type-3",
    "Fuel-1", "Fuel-2", "Fuel-3", "MW-1", "MW-2", "MW-3", "Net MWs to Grid",
    "Full Capacity, Partial or Energy Only (FC/P/EO)", "Off-Peak Deliverability and Economic Only",
    "County", "State", "Utility", "Station or Transmission Line",
    "Proposed\nOn-line Date\n(as filed with IR)", "Current\nOn-line Date",
    "Feasibility Study or Supplemental Review", "System Impact Study or \nPhase I Cluster Study",
    "Facilities Study (FAS) or \nPhase II Cluster Study", "Optional Study\n(OS)",
    "Interconnection Agreement \nStatus", "Reason for Withdrawal",
]

FOOTER = ("The contents of these pages are subject to change without notice.  Decisions based on "
          "information contained within the California ISO's web site are the visitor's sole responsibility.")

PQ_ROWS = {
    "Grid GenerationQueue": [
        # hybrid solar + storage; net MW < component MW; header-cell "1,250" style number on net
        ["HYBRID ONE", 1001, D(2021, 4, 1), D(2021, 4, 15, 7), "ACTIVE", "Cluster 14",
         "Photovoltaic", "Storage", None, "Solar", "Battery", None, 200, 150, None, 200,
         "Full Capacity", 100, "Off-Peak Deliverability", "Group A", "KERN COUNTY", "CA", "SCE", "SCE",
         "Whirlwind Substation 230 kV", D(2026, 6, 30, 7), D(2027, 6, 30, 7), None,
         "Complete", "Complete", "Complete", "None", "Executed"],
        # standalone storage, comma-formatted MW string, dirty county, line POI
        ["STANDALONE BESS", 1002, D(2022, 4, 1), D(2022, 4, 15, 7), "ACTIVE", "Cluster 14",
         "Storage", None, None, "Battery", None, None, "1,250", None, None, "1,250",
         "Energy Only", None, None, None, "MERCED / FRESNO", "CA", "PGAE", "Fresno",
         "Vaca-Dixon 230 kV", D(2026, 6, 30, 7), D(2028, 12, 31, 8), None,
         "Complete", "Complete", "In Progress", "None", "Pending"],
        # gas peaker: no storage flags
        ["GAS PEAKER", "1003A", D(2010, 1, 1), D(2010, 1, 15, 8), "ACTIVE", "Serial LGIP",
         "Combustion Turbine", None, None, "Natural Gas", None, None, 50, None, None, 50,
         "Full Capacity", 100, "Off-Peak Deliverability", "Group B", "L.A", "CA", "SCE", "SCE",
         "Vincent 500 kV", D(2012, 6, 30, 7), D(2027, 1, 1, 8), None,
         "Complete", "Complete", "Complete", "None", "Executed"],
    ],
    "Completed Generation Projects": [
        ["OPERATING SOLAR", 2001, D(2015, 1, 1), D(2015, 1, 10, 8), "COMPLETED", "Cluster 7",
         "Photovoltaic", None, None, "Solar", None, None, 80, None, None, 80,
         "Full Capacity", 100, "Off-Peak Deliverability", None, "KINGS AND FRESNO", "CA", "PGAE", "Fresno",
         "Whirlwind Substation 230 kV", D(2017, 6, 30, 7), D(2018, 3, 1, 8),
         "Complete", "Complete", "Complete", "None", "Executed"],
    ],
    "Withdrawn Generation Projects": [
        # withdrew after Phase II results were in hand (recent)
        ["DEAD WIND", 3001, D(2019, 1, 1), D(2019, 1, 10, 8), "WITHDRAWN", D(2024, 3, 1, 17, 56, 36),
         "Cluster 12", "Wind Turbine", "Storage", None, "Wind", "Battery", None, 120, 60, None, 120,
         "Full Capacity", "Off-Peak Deliverability", "SAN BERNADINO", "CA", "SCE",
         "Whirlwind Substation 230 kV", D(2022, 6, 30, 7), D(2025, 6, 30, 7),
         "Complete", "Complete", "Complete", "None", "None", "IC Request"],
        # withdrew before Phase II (old)
        ["DEAD SOLAR", 3002, D(2011, 1, 1), D(2011, 1, 10, 8), "WITHDRAWN", D(2013, 5, 1, 12),
         "Cluster 4", "Photovoltaic", None, None, "Solar", None, None, 300, None, None, 300,
         "Energy Only", None, "MOJAVE", "AZ", "SCE",
         "North Gila - Hoodoo Wash 500 kV", D(2014, 6, 30, 7), D(2015, 6, 30, 7),
         "Complete", "Complete", "In Progress", "None", "None", "IC Request"],
    ],
}
PQ_HEADERS = {
    "Grid GenerationQueue": PQ_HEADER_ACTIVE,
    "Completed Generation Projects": PQ_HEADER_COMPLETED,
    "Withdrawn Generation Projects": PQ_HEADER_WITHDRAWN,
}


def write_queue_xlsx(path: Path, header_overrides: dict[str, str] | None = None,
                     footer: bool = False, run_date: str | None = "09/07/2026",
                     rows: dict[str, list[list]] | None = None) -> Path:
    """Write a workbook with CAISO's public-queue layout: run-date stamp in row 1, title in
    row 2, group headers in row 3, column names in row 4, data from row 5.

    `rows` replaces the default project rows for the sheets it names (others keep theirs), so a
    test can exercise one filing shape without disturbing the counts every other test asserts."""
    header_overrides = header_overrides or {}
    rows = rows or {}
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet, header in PQ_HEADERS.items():
        ws = wb.create_sheet(sheet)
        ws.append([f"Report Run Date: {run_date}"] if run_date else [None])
        ws.append(["The California ISO Controlled Grid Generation Queue for All: test"])
        ws.append(["Generating Facility", None, None, None, None, None, "MWs"])
        ws.append([header_overrides.get(h, h) for h in header])
        for row in rows.get(sheet, PQ_ROWS[sheet]):
            assert len(row) == len(header), (sheet, len(row), len(header))
            ws.append(row)
        if footer:
            ws.append([None])
            ws.append([FOOTER])
    wb.save(path)
    return path


@pytest.fixture
def queue_xlsx(tmp_path: Path) -> Path:
    return write_queue_xlsx(tmp_path / "publicqueuereport.xlsx")


# ---------------------------------------------------------------------- cluster 15

C15_HEADER_ACTIVE = [
    "Queue Number", "Project Number", "Project Name", "Generation/Fuel 1", "NET MW 1",
    "Generation/Fuel 2", "NET MW 2", "Generation/Fuel 3", "NET MW 3", "NET MW POI", "PROJECT COUNTY",
    "Project State", "Study Area", "PTO", "POI", "Voltage kV", "Requested COD", "Queue Date ",
    "Application Date", "Service Type",
]
C15_HEADER_WITHDRAWN = [
    "Queue Number", "Project Number", "Project Name", "Generation/Fuel 1", "NET MW 1",
    "Generation/Fuel 2", "NET MW 2", "Generation/Fuel 3", "NET MW 3", "NET MW POI", "PROJECT COUNTY",
    "Project State", "Study Area", "PTO", "POI", "Voltage kV", "Requested COD", "Queue Date",
    "Application Date ", "Withdrawal Date", "Service Type",
]
C15_ROWS = {
    "Cluster 15 ": [
        [2207, 54516, "Alisa Solar Energy Complex 2", "Photovoltaic/Solar", 500, "Storage/Battery", 500,
         "N/A", "N/A", 500, "Yuma", "AZ", "SAN DIEGO", "SDGE", "NORTH GILA - HOODOO WASH (SDGE Portion Only)",
         525, D(2030, 6, 1), D(2025, 2, 12), D(2024, 11, 18), "Energy Only Requested"],
        [2244, 54963, "Annapurna", "Storage/Battery", 257, "N/A", "N/A", "N/A", "N/A", 250,
         "Merced County", "CA", "PG&E FRESNO", "PGAE", "QUINTO SW STA 230 kV", 230,
         D(2028, 6, 1), D(2025, 2, 12), D(2024, 11, 20), "Full Capacity Deliverability Status Requested"],
        [2301, 55001, "Whirlwind Storage", "Storage/Battery", 400, "N/A", "N/A", "N/A", "N/A", 400,
         "San Bernadino", "CA", "SCE NOL", "SCE", "WHIRLWIND 230 kV", 230,
         D(2029, 6, 1), D(2025, 2, 12), D(2024, 11, 20), "Merchant- Full Capacity Deliverability Status Requested"],
    ],
    "Withdrawn": [
        [2229, 54899, "Clay Flats", "Storage/Battery", 437.08, "N/A", "N/A", "N/A", "N/A", 425,
         "king", "CA", "PG&E FRESNO", "LSPC", "MANNING 500 kV", 500,
         D(2030, 10, 1), D(2025, 2, 12), D(2024, 11, 22), D(2025, 4, 23), "Energy Only Requested"],
        [2283, 54729, "Amargosa SEZ", "Photovoltaic/Solar", 510.35, "Storage/Battery", 508.19, "N/A", "N/A", 500,
         "Nye", "NV", "SCE EOP", "GLW", "BEATTY 230 kV", 230,
         D(2030, 12, 1), D(2025, 2, 12), D(2024, 11, 18), D(2025, 4, 25),
         "Merchant- Full Capacity Deliverability Status Requested"],
    ],
}


def write_cluster15_xlsx(path: Path, sheet_names: tuple[str, str] = ("Cluster 15 ", "Withdrawn")) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for (key, header), name in zip((("Cluster 15 ", C15_HEADER_ACTIVE), ("Withdrawn", C15_HEADER_WITHDRAWN)),
                                   sheet_names, strict=True):
        ws = wb.create_sheet(name)
        ws.append(header)
        for row in C15_ROWS[key]:
            assert len(row) == len(header), (key, len(row), len(header))
            ws.append(row)
    wb.save(path)
    return path


@pytest.fixture
def cluster15_xlsx(tmp_path: Path) -> Path:
    return write_cluster15_xlsx(tmp_path / "cluster15.xlsx")


# ----------------------------------------------------------------------- real data

def _need(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"real data file missing: {path}")
    return path


@pytest.fixture(scope="session")
def real_queue_path() -> Path:
    return _need(DATA / "publicqueuereport.xlsx")


@pytest.fixture(scope="session")
def real_cluster15_path() -> Path:
    return _need(DATA / "cluster15.xlsx")


@pytest.fixture(scope="session")
def real_pq(real_queue_path: Path) -> pd.DataFrame:
    from caiso_siting import queue_report
    return queue_report.load_all(real_queue_path)


@pytest.fixture(scope="session")
def real_c15(real_cluster15_path: Path) -> pd.DataFrame:
    from caiso_siting import cluster15
    return cluster15.load(real_cluster15_path)


@pytest.fixture(scope="session")
def real_projects(real_queue_path: Path, real_cluster15_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    from caiso_siting import nodes
    if nodes.DATA.resolve() != DATA.resolve() or config.DATA.resolve() != DATA.resolve():
        pytest.skip(f"package DATA resolved to {nodes.DATA}, not the repo's {DATA}")
    return nodes.load_projects()


@pytest.fixture(scope="session")
def real_nodes(real_projects) -> pd.DataFrame:
    from caiso_siting import nodes
    pq, c15 = real_projects
    return nodes.build_nodes(pq, c15)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_data: touches the real CAISO files under data/")
