"""Staleness is measured against each source's own cadence, never against "is this today's file"."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from caiso_siting import freshness


def reg(**over) -> pd.DataFrame:
    row = dict(source_id="s", label="S", artifact="", cadence="annual", cadence_days=365,
               as_of_method="manual", published="2026-01-01", vintage="", stale_days=425,
               expired_days=550, on_expired="mark", feeds="x_", note="")
    row.update(over)
    df = pd.DataFrame([row])
    for c in ("cadence_days", "stale_days", "expired_days"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def sev(today, **over) -> str:
    return freshness.check("s", today=date.fromisoformat(today), registry=reg(**over)).severity


def test_cadence_relative_not_absolute():
    """An annual report eleven months old is current. A monthly file two months old is not."""
    assert sev("2026-11-01") == freshness.FRESH          # annual, 304 days
    assert sev("2026-11-01", cadence="monthly", cadence_days=30, stale_days=60,
               expired_days=120) == freshness.EXPIRED


def test_thresholds():
    assert sev("2027-02-01") == freshness.FRESH          # 396 days, inside stale_days=425
    assert sev("2027-04-01") == freshness.STALE          # past stale_days, inside expired_days
    assert sev("2027-08-01") == freshness.EXPIRED


def test_archival_never_expires():
    assert sev("2040-01-01", cadence="archival", stale_days=float("nan"),
               expired_days=float("nan")) == freshness.FRESH


def test_missing_artifact_beats_every_other_severity(tmp_path):
    st = freshness.check("s", today=date(2026, 1, 2), registry=reg(artifact="nope.xlsx"), root=tmp_path)
    assert st.severity == freshness.MISSING and not st.publishable


def test_undated_is_never_fresh():
    assert sev("2026-01-02", published="") == freshness.UNDATED


def test_withhold_vs_mark():
    e = freshness.check("s", today=date(2027, 8, 1), registry=reg(on_expired="withhold"))
    assert e.severity == freshness.EXPIRED and not e.publishable
    m = freshness.check("s", today=date(2027, 8, 1), registry=reg(on_expired="mark"))
    assert m.severity == freshness.EXPIRED and m.publishable and m.marked


def test_gate_raises_only_for_fail_sources():
    st = freshness.check("s", today=date(2027, 8, 1), registry=reg(on_expired="fail"))
    with pytest.raises(freshness.SourceExpired):
        freshness.gate(st, log=lambda *_: None)
    ok = freshness.check("s", today=date(2027, 8, 1), registry=reg(on_expired="mark"))
    assert freshness.gate(ok, log=lambda *_: None) is True


def test_the_real_registry_loads_and_every_row_resolves():
    d = freshness.load_registry()
    assert len(d) >= 8
    assert set(d.on_expired) <= {"fail", "withhold", "mark"}
    st = freshness.check_all()
    assert set(st) == set(d.source_id)
    for s in st.values():
        assert s.severity in (freshness.FRESH, freshness.STALE, freshness.EXPIRED,
                              freshness.UNDATED, freshness.MISSING)
