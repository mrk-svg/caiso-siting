"""diff.py: every change class from two synthetic snapshots, the mixed date-format fix, and a
snapshot -> load -> diff round trip on the real data (redirected to tmp_path)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from caiso_siting import diff

BASE = {
    "sheet_status": "ACTIVE", "net_mw": 100.0, "storage_mw": 50.0, "current_cod": "2027-06-30 07:00:00",
    "ia_status": "Pending", "deliverability": "FULL CAPACITY", "tpd_group": "GROUP A",
    "poi": "WHIRLWIND SUBSTATION 230 KV", "county": "KERN", "utility": "SCE", "project_name": "P",
    "cluster": "CLUSTER 14", "node_key": "WHIRLWIND", "poi_base": "WHIRLWIND SUBSTATION",
    "report": "PUBLIC", "queue_position": "1",
}


def row(key: str, **over) -> dict:
    r = {**BASE, "project_name": key.split(":")[1], "queue_position": key.split(":")[1], **over}
    r["report"] = key.split(":")[0]
    r["key"] = key
    return r


def write_snapshot(d: Path, rows: list[dict]) -> Path:
    """Mirror diff.snapshot(): TRACKED + report + queue_position, index named 'key'."""
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows).set_index("key")[diff.TRACKED + ["report", "queue_position"]]
    df.to_csv(d / "projects.csv")
    return d


def test_tracked_columns_are_the_newsletter_fields():
    assert diff.TRACKED == ["sheet_status", "net_mw", "storage_mw", "current_cod", "ia_status", "deliverability",
                            "tpd_group", "poi", "county", "utility", "project_name", "cluster", "node_key",
                            "poi_base"]


def test_load_snapshot_parses_mixed_date_formats(tmp_path):
    d = write_snapshot(tmp_path / "2026-09-07", [
        row("PUBLIC:1", current_cod="2027-06-30 07:00:00"),   # public report style (with time)
        row("C15:2", current_cod="2031-06-30"),               # date-only style
        row("PUBLIC:3", current_cod=""),
    ])
    s = diff.load_snapshot(d)
    assert s.index.name == "key"
    assert s.loc["PUBLIC:1", "current_cod"] == pd.Timestamp("2027-06-30 07:00:00")
    assert s.loc["C15:2", "current_cod"] == pd.Timestamp("2031-06-30")       # NOT NaT
    assert pd.isna(s.loc["PUBLIC:3", "current_cod"])
    assert s.queue_position.dtype == object or pd.api.types.is_string_dtype(s.queue_position)
    assert s.net_mw.dtype == float and s.storage_mw.dtype == float


@pytest.fixture
def pair(tmp_path):
    a = write_snapshot(tmp_path / "2026-09-07", [
        row("PUBLIC:1"),                                                 # unchanged
        row("PUBLIC:2"),                                                 # -> WITHDRAWN
        row("PUBLIC:3"),                                                 # -> COMPLETED
        row("PUBLIC:4", net_mw=250.0),                                   # -> MW_CHANGE (downsized)
        row("PUBLIC:5", current_cod="2027-06-30 07:00:00"),              # -> COD_SLIP (mixed formats)
        row("PUBLIC:6", current_cod="2031-06-30"),                       # -> COD_PULLED_IN
        row("PUBLIC:7", ia_status="Pending"),                            # -> IA_STATUS
        row("PUBLIC:8", deliverability="ENERGY ONLY", tpd_group=""),     # -> DELIV_CHANGE (deliverability)
        row("PUBLIC:9", tpd_group="GROUP B"),                            # -> DELIV_CHANGE (tpd_group)
        row("PUBLIC:10", poi="VINCENT 500 KV", poi_base="VINCENT"),      # -> POI_CHANGE
        row("PUBLIC:11"),                                                # -> GONE
        row("C15:2301", report="C15", cluster="C15", ia_status="", tpd_group="", current_cod=""),  # NA fields
        row("PUBLIC:12", net_mw=100.0),                                  # 0.3 MW wobble: no change
    ])
    b = write_snapshot(tmp_path / "2026-09-14", [
        row("PUBLIC:1"),
        row("PUBLIC:2", sheet_status="WITHDRAWN"),
        row("PUBLIC:3", sheet_status="COMPLETED"),
        row("PUBLIC:4", net_mw=200.0),
        row("PUBLIC:5", current_cod="2031-06-30"),
        row("PUBLIC:6", current_cod="2029-12-31 08:00:00"),
        row("PUBLIC:7", ia_status="Executed"),
        row("PUBLIC:8", deliverability="FULL CAPACITY", tpd_group=""),
        row("PUBLIC:9", tpd_group="GROUP C"),
        row("PUBLIC:10", poi="WHIRLWIND SUBSTATION 230 KV"),
        row("C15:2301", report="C15", cluster="C15", ia_status="", tpd_group="", current_cod=""),
        row("PUBLIC:12", net_mw=100.3),
        row("C15:2400", report="C15", cluster="C15", ia_status="", tpd_group="", current_cod="",
            project_name="Newcomer", net_mw=300.0),                      # -> NEW
    ])
    return diff.load_snapshot(a), diff.load_snapshot(b)


def test_every_change_class(pair):
    a, b = pair
    changes, tots = diff.diff(a, b, "2026-09-07", "2026-09-14")
    assert list(changes.columns) == ["key", "change", "project", "poi", "county", "mw", "detail"]
    by = changes.set_index("key")

    assert by.loc["C15:2400", "change"] == "NEW"
    assert by.loc["C15:2400", "detail"] == "ACTIVE C15" and by.loc["C15:2400", "mw"] == 300.0
    assert by.loc["C15:2400", "project"] == "Newcomer"

    assert by.loc["PUBLIC:11", "change"] == "GONE" and by.loc["PUBLIC:11", "detail"] == "was ACTIVE"

    assert by.loc["PUBLIC:2", "change"] == "WITHDRAWN" and by.loc["PUBLIC:2", "detail"] == "ACTIVE -> WITHDRAWN"
    assert by.loc["PUBLIC:3", "change"] == "COMPLETED" and by.loc["PUBLIC:3", "detail"] == "ACTIVE -> COMPLETED"

    assert by.loc["PUBLIC:4", "change"] == "MW_CHANGE" and by.loc["PUBLIC:4", "detail"] == "250 -> 200 MW"
    assert by.loc["PUBLIC:4", "mw"] == 200.0                          # the later value is reported

    assert by.loc["PUBLIC:5", "change"] == "COD_SLIP"
    assert by.loc["PUBLIC:5", "detail"].startswith("2027-06-30 -> 2031-06-30 (+")
    assert by.loc["PUBLIC:5", "detail"].endswith(" d)")
    assert by.loc["PUBLIC:6", "change"] == "COD_PULLED_IN"
    assert by.loc["PUBLIC:6", "detail"].startswith("2031-06-30 -> 2029-12-31 (-")

    assert by.loc["PUBLIC:7", "change"] == "IA_STATUS"
    assert by.loc["PUBLIC:7", "detail"] == "ia_status: Pending -> Executed"

    assert by.loc["PUBLIC:8", "change"] == "DELIV_CHANGE"
    assert by.loc["PUBLIC:8", "detail"] == "deliverability: ENERGY ONLY -> FULL CAPACITY"
    assert by.loc["PUBLIC:9", "change"] == "DELIV_CHANGE"
    assert by.loc["PUBLIC:9", "detail"] == "tpd_group: GROUP B -> GROUP C"

    assert by.loc["PUBLIC:10", "change"] == "POI_CHANGE"
    assert by.loc["PUBLIC:10", "detail"] == "poi: VINCENT 500 KV -> WHIRLWIND SUBSTATION 230 KV"

    # exactly one row per changed project, nothing for unchanged / NA-only / sub-threshold rows
    assert "PUBLIC:1" not in by.index and "C15:2301" not in by.index and "PUBLIC:12" not in by.index
    assert by.index.is_unique
    assert changes.change.value_counts().to_dict() == {
        "NEW": 1, "GONE": 1, "WITHDRAWN": 1, "COMPLETED": 1, "MW_CHANGE": 1, "COD_SLIP": 1,
        "COD_PULLED_IN": 1, "IA_STATUS": 1, "DELIV_CHANGE": 2, "POI_CHANGE": 1,
    }


def test_cod_slip_days_computed_from_mixed_formats(pair):
    a, b = pair
    changes, _ = diff.diff(a, b, "a", "b")
    detail = changes.set_index("key").loc["PUBLIC:5", "detail"]
    expected = (pd.Timestamp("2031-06-30") - pd.Timestamp("2027-06-30 07:00:00")).days
    assert detail == f"2027-06-30 -> 2031-06-30 (+{expected} d)"
    assert expected > 1400


def test_totals(pair):
    a, b = pair
    _, tots = diff.diff(a, b, "a", "b")
    assert set(tots) == {"a", "b"}
    ta, tb = tots["a"], tots["b"]
    assert ta["active_n"] == 13 and tb["active_n"] == 11              # 2 left ACTIVE, 1 GONE, 1 NEW
    assert ta["withdrawn_n"] == 0 and tb["withdrawn_n"] == 1
    assert ta["c15_active_n"] == 1 and tb["c15_active_n"] == 2
    assert tb["c15_active_mw"] == 400.0
    assert tb["active_mw"] == pytest.approx(b[b.sheet_status == "ACTIVE"].net_mw.sum())


def test_multiple_changes_on_one_project_each_get_a_row(tmp_path):
    a = diff.load_snapshot(write_snapshot(tmp_path / "a", [row("PUBLIC:1", net_mw=500.0, ia_status="Pending")]))
    b = diff.load_snapshot(write_snapshot(tmp_path / "b", [row("PUBLIC:1", net_mw=100.0, ia_status="Executed",
                                                              sheet_status="WITHDRAWN")]))
    changes, _ = diff.diff(a, b, "a", "b")
    assert changes.change.tolist() == ["WITHDRAWN", "MW_CHANGE", "IA_STATUS"]


def test_storage_component_change_with_net_unchanged_is_reported(tmp_path):
    # 2026-09-14: SOLAR STAR 3/4 at WHIRLWIND went 24 -> 23 MW storage on an unchanged 24 MW net; the
    # header total moved by -2 MW with no row explaining it.
    a = diff.load_snapshot(write_snapshot(tmp_path / "a", [row("PUBLIC:1", net_mw=24.0, storage_mw=24.0)]))
    b = diff.load_snapshot(write_snapshot(tmp_path / "b", [row("PUBLIC:1", net_mw=24.0, storage_mw=23.0)]))
    changes, _ = diff.diff(a, b, "a", "b")
    assert changes.change.tolist() == ["STORAGE_CHANGE"]
    assert changes.detail.iloc[0] == "storage 24 -> 23 MW (net unchanged)"
    # a net change already carries the row; storage is not double-reported
    c = diff.load_snapshot(write_snapshot(tmp_path / "c", [row("PUBLIC:1", net_mw=20.0, storage_mw=20.0)]))
    changes, _ = diff.diff(a, c, "a", "c")
    assert changes.change.tolist() == ["MW_CHANGE"]


def test_status_change_outside_known_classes_is_labelled_status(tmp_path):
    a = diff.load_snapshot(write_snapshot(tmp_path / "a", [row("PUBLIC:1", sheet_status="WITHDRAWN")]))
    b = diff.load_snapshot(write_snapshot(tmp_path / "b", [row("PUBLIC:1", sheet_status="ACTIVE")]))
    changes, _ = diff.diff(a, b, "a", "b")
    assert changes.change.tolist() == ["STATUS"] and changes.detail.iloc[0] == "WITHDRAWN -> ACTIVE"


def test_nan_to_blank_is_not_a_change(tmp_path):
    a = diff.load_snapshot(write_snapshot(tmp_path / "a", [row("PUBLIC:1", ia_status="", current_cod="")]))
    b = diff.load_snapshot(write_snapshot(tmp_path / "b", [row("PUBLIC:1", ia_status="", current_cod="2030-01-01")]))
    changes, _ = diff.diff(a, b, "a", "b")
    assert changes.empty                        # NaN COD -> date is not reported as a slip


def test_identical_snapshots_yield_no_changes(pair):
    a, _ = pair
    changes, _ = diff.diff(a, a.copy(), "a", "a")
    assert changes.empty


def test_write_report(pair, monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(diff, "OUT", out)
    a, b = pair
    changes, tots = diff.diff(a, b, "2026-09-07", "2026-09-14")
    diff.write_report(changes, tots, "2026-09-07", "2026-09-14")
    md = (out / "diff_latest.md").read_text()
    assert md.startswith("# CAISO queue diff — 2026-09-07 → 2026-09-14")
    assert "## Changes (11)" in md and "COD_PULLED_IN" in md and "Newcomer" in md
    assert "| Active projects | 13 | 11 | -2 |" in md
    csv = pd.read_csv(out / "diff_latest.csv")
    assert len(csv) == 11 and set(csv.change) == set(changes.change)


def test_write_report_no_changes(pair, monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(diff, "OUT", out)
    a, _ = pair
    changes, tots = diff.diff(a, a, "x", "y")
    diff.write_report(changes, tots, "x", "y")
    assert "No row-level changes between snapshots." in (out / "diff_latest.md").read_text()


# ------------------------------------------------------------- real data round trip

def footer_rows(df: pd.DataFrame) -> pd.Series:
    """CAISO's per-sheet disclaimer paragraph survives parsing (queue_report.py:109) and reaches the
    snapshot with key NaN / 'PUBLIC:nan'. Tests below mask it out explicitly."""
    return df.index.isna() | df.index.astype(str).str.endswith(":nan")


@pytest.mark.real_data
def test_load_pair_has_no_footer_key(real_queue_path):
    live = diff.load_pair()
    assert not footer_rows(live).any(), live[footer_rows(live)].project_name.str[:60].tolist()


@pytest.mark.real_data
def test_snapshot_round_trip_on_real_data(monkeypatch, tmp_path, real_queue_path, real_cluster15_path):
    snap = tmp_path / "snapshots"
    monkeypatch.setattr(diff, "SNAP", snap)                # never write into data/snapshots/
    d = diff.snapshot()
    assert d.parent == snap and (d / "projects.csv").exists()
    assert (d / "publicqueuereport.xlsx").exists() and (d / "cluster15.xlsx").exists()
    s = diff.load_snapshot(d)
    assert list(s.columns) == diff.TRACKED + ["report", "queue_position"]
    s = s[~footer_rows(s)]                                  # see test_load_pair_has_no_footer_key
    assert s.index.is_unique and s.index.str.match(r"^(PUBLIC|C15):").all()
    assert set(s.report) == {"PUBLIC", "C15"}
    assert (s.sheet_status == "ACTIVE").sum() > 250
    # mixed COD formats inside one file must all parse (the format='mixed' fix)
    pub = s[(s.report == "PUBLIC") & (s.sheet_status == "ACTIVE")]
    assert pub.current_cod.notna().mean() > 0.9
    changes, tots = diff.diff(s, s, "a", "b")
    assert changes.empty
    assert tots["a"] == tots["b"]


@pytest.mark.real_data
def test_committed_snapshot_loads_and_matches_live_parse(real_queue_path):
    committed = diff.SNAP / "2026-09-07"
    if not (committed / "projects.csv").exists():
        pytest.skip("no committed snapshot")
    s = diff.load_snapshot(committed)
    assert s.current_cod.notna().sum() > 1000
    live = diff.load_pair()
    s, live = s[~footer_rows(s)], live[~footer_rows(live)]
    changes, _ = diff.diff(s, live, "committed", "live")
    # same source files -> no NEW/GONE rows between the committed snapshot and a fresh parse
    assert not changes.change.isin(["NEW", "GONE"]).any(), changes.head(20).to_string()
