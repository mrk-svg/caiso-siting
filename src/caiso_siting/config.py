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


# --- CSV writing ------------------------------------------------------------
# A cell beginning = + - @ (or a tab/CR) is executed as a formula when the file is opened in Excel
# or LibreOffice. Our audience opens spreadsheets, and the cell values come from CAISO and PG&E
# workbooks we do not control, so every string cell is escaped on write. Numbers are untouched:
# a negative longitude is not a formula.
_FORMULA_LEAD = ("=", "+", "@", "\t", "\r")


def _is_formula(v) -> bool:
    if not isinstance(v, str) or not v:
        return False
    if v[0] in _FORMULA_LEAD:
        return True
    # "-" only matters when what follows is not a number: -118.25 is a longitude, -cmd is a payload
    return v[0] == "-" and not (v[1:2].isdigit() or v[1:2] == ".")


def csv_safe(df):
    """Return a copy of `df` with formula-leading string cells prefixed by a single quote."""
    out = df.copy()
    for c in out.columns:
        col = out[c]
        if col.dtype != object:
            continue
        # .map over an object column returns object dtype; pandas will not use that as a boolean
        # mask, so the escape silently did nothing until this astype(bool) was added.
        mask = col.map(_is_formula).astype(bool)
        if mask.any():
            out.loc[mask, c] = col[mask].map(lambda v: "'" + v)
    return out


def write_csv(df, path, **kw):
    """to_csv with the formula guard applied. Use this instead of df.to_csv for anything we ship."""
    csv_safe(df).to_csv(path, index=kw.pop("index", False), **kw)
    return path
