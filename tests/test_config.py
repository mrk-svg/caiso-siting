"""config.py: root resolution and provenance helpers."""
from __future__ import annotations

import re

import openpyxl
import pandas as pd
from conftest import REPO_ROOT

from caiso_siting import config


def test_find_root_prefers_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("CAISO_SITING_ROOT", str(tmp_path))
    assert config.find_root() == tmp_path.resolve()


def test_find_root_walks_up_to_nearest_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("CAISO_SITING_ROOT", raising=False)
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    deep = root / "a" / "b"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert config.find_root() == root.resolve()


def test_find_root_falls_back_to_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("CAISO_SITING_ROOT", raising=False)
    lone = tmp_path / "lone"
    lone.mkdir()
    monkeypatch.chdir(lone)
    # no data/ anywhere above tmp (pytest's tmp tree has none) -> cwd itself
    assert config.find_root() == lone.resolve()


def test_module_paths_point_at_repo():
    assert config.ROOT == REPO_ROOT.resolve()
    assert config.DATA == config.ROOT / "data"
    assert config.OUT == config.ROOT / "outputs"
    assert config.SNAPSHOTS == config.DATA / "snapshots"


def test_add_provenance_and_run_stamp():
    df = pd.DataFrame({"x": [1, 2]})
    out = config.add_provenance(df, "f.xlsx", "2026-09-07")
    assert out is df
    assert out.source_file.tolist() == ["f.xlsx", "f.xlsx"]
    assert (out.source_run_date == "2026-09-07").all()
    assert out.pipeline_commit.nunique() == 1 and out.pipeline_commit.iloc[0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", config.run_stamp())
    assert (config.add_provenance(pd.DataFrame({"x": [1]}), "g.xlsx").source_run_date == "").all()


def test_xlsx_run_date_parses_caiso_stamp(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Report Run Date: 09/07/2026"])
    ws2 = wb.create_sheet("other")
    ws2.append(["Report Run Date: 01/02/2025"])
    p = tmp_path / "r.xlsx"
    wb.save(p)
    assert config.xlsx_run_date(p) == "2026-09-07"
    assert config.xlsx_run_date(p, sheet="other") == "2025-01-02"
    assert config.xlsx_run_date(p, pattern="Nope") is None


def test_xlsx_run_date_bad_file_returns_none(tmp_path):
    p = tmp_path / "not.xlsx"
    p.write_text("nope")
    assert config.xlsx_run_date(p) is None
    assert config.xlsx_run_date(tmp_path / "missing.xlsx") is None
