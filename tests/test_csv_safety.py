"""Every CSV this project ships is opened in a spreadsheet by someone. A cell beginning = + - @
is executed as a formula there, and the cell values come from CAISO and PG&E workbooks we do not
control. SECURITY.md claims these files are guarded; this is the guard."""
from __future__ import annotations

import glob
import os

import pandas as pd

from caiso_siting.config import csv_safe

DANGEROUS = ("=", "+", "@", "\t", "\r")


def test_formula_leading_strings_are_neutralised():
    df = pd.DataFrame({
        "name": ['=HYPERLINK("https://evil","click")', "@SUM(A1:A9)", "+1+1", "-cmd|' /c calc'!A0",
                 "Normal Substation", "-118.25", "-0.5"],
        "mw": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
    })
    out = csv_safe(df)
    for v in out.name[:4]:
        assert v.startswith("'"), v
    assert out.name[4] == "Normal Substation"
    assert out.name[5] == "-118.25", "a negative longitude is not a formula"
    assert out.name[6] == "-0.5"
    assert list(out.mw) == list(df.mw), "numeric columns are untouched"


def test_csv_safe_does_not_mutate_the_input():
    df = pd.DataFrame({"a": ["=BAD()"]})
    csv_safe(df)
    assert df.a[0] == "=BAD()"


def test_shipped_outputs_contain_no_live_formula_cell():
    """The real files, as they sit in the repo right now."""
    paths = sorted(glob.glob("outputs/*.csv")) + sorted(glob.glob("data/snapshots/*/projects.csv"))
    if not paths:
        return  # a fresh clone before the first run
    bad = []
    for p in paths:
        if os.path.getsize(p) > 8_000_000:
            continue
        df = pd.read_csv(p, dtype=str, keep_default_na=False, low_memory=False)
        for c in df.columns:
            for v in df[c]:
                if isinstance(v, str) and v.startswith(DANGEROUS):
                    bad.append((p, c, v[:40]))
    assert not bad, f"live formula cells in shipped CSVs: {bad[:5]}"
