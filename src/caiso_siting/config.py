"""Paths and provenance shared by every command.

Project root resolution, in order: CAISO_SITING_ROOT env var, else the first parent of the
current directory that contains a `data/` folder, else the current directory.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def find_root() -> Path:
    env = os.environ.get("CAISO_SITING_ROOT")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for p in (here, *here.parents):
        if (p / "data").is_dir():
            return p
    return here


ROOT = find_root()
DATA = ROOT / "data"
OUT = ROOT / "outputs"
SNAPSHOTS = DATA / "snapshots"
SITE = ROOT / "site"

PUBLIC_QUEUE_URL = "https://www.caiso.com/documents/publicqueuereport.xlsx"
CLUSTER15_URL = "https://www.caiso.com/documents/cluster-15-interconnection-requests.xlsx"

RECENT_YEARS = 5


def pipeline_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def run_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_provenance(df: pd.DataFrame, source_file: str, source_run_date: str | None = None) -> pd.DataFrame:
    """Every output row says which file it came from, when CAISO ran that file, and which
    pipeline commit produced it. Cheap now; indispensable the first time a number is challenged."""
    df["source_file"] = source_file
    df["source_run_date"] = source_run_date or ""
    df["pipeline_commit"] = pipeline_commit()
    df["pipeline_run"] = run_stamp()
    return df


def xlsx_run_date(path: Path, sheet: int | str = 0, pattern: str = "Report Run Date") -> str | None:
    """CAISO stamps 'Report Run Date: MM/DD/YYYY' in the first rows of each sheet."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
        for row in ws.iter_rows(min_row=1, max_row=5, values_only=True):
            for cell in row:
                if isinstance(cell, str) and pattern in cell:
                    raw = cell.split(":", 1)[-1].strip()
                    return pd.to_datetime(raw, errors="coerce").strftime("%Y-%m-%d") if raw else None
    except Exception:  # noqa: BLE001
        return None
    return None
