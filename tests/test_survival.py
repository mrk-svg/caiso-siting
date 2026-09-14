"""survival.py: Kaplan–Meier by hand on a synthetic cohort, the censoring rules, MW weighting,
the SVG renderer, and a smoke test on the real reports."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from caiso_siting import survival

RUN = pd.Timestamp("2026-09-07")
Q = pd.Timestamp("2020-04-15")


def frame(rows: list[dict]) -> pd.DataFrame:
    """Minimal project frame: sheet_status, queue_date, withdrawn_date, actual_cod, net_mw, cluster + flags."""
    base = dict(cluster="C13", queue_date=Q, withdrawn_date=pd.NaT, actual_cod=pd.NaT, net_mw=100.0,
                is_standalone_storage=False, has_solar=False, has_storage=False)
    return pd.DataFrame([{**base, **r} for r in rows])


def months(n: int) -> pd.Timestamp:
    return Q + pd.DateOffset(months=n)


# Five projects: withdrawals at months 6, 12, 12; one censored (ACTIVE) at 24; one censored at 3.
# By hand:  S(0..5) = 1;  m6: 4 at risk, 1 event -> 3/4;  m12: 3 at risk, 2 events -> 3/4 * 1/3 = 1/4;
#           m24: 1 at risk, censored -> 1/4;  beyond 24 nobody is at risk -> NaN.
HAND = [
    dict(sheet_status="WITHDRAWN", withdrawn_date=months(6)),
    dict(sheet_status="WITHDRAWN", withdrawn_date=months(12)),
    dict(sheet_status="WITHDRAWN", withdrawn_date=months(12)),
    dict(sheet_status="ACTIVE"),                                   # censored at run date, 24 months later
    dict(sheet_status="COMPLETED", actual_cod=months(3)),          # censored at its COD, month 3
]


def test_kaplan_meier_matches_hand_computation():
    lt, excluded = survival.lifetimes(frame(HAND), months(24))
    assert lt["t"].tolist() == [6, 12, 12, 24, 3]
    assert lt["event"].tolist() == [True, True, True, False, False]
    assert excluded == {"excluded_no_queue_date": 0, "excluded_withdrawn_no_date": 0, "excluded_end_before_queue": 0}
    km = survival.kaplan_meier(lt, max_month=30, min_at_risk=1)
    s = km.set_index("month")["survival"]
    assert s.loc[0] == 1.0 and s.loc[5] == 1.0
    assert s.loc[6] == pytest.approx(0.75)
    assert s.loc[11] == pytest.approx(0.75)
    assert s.loc[12] == pytest.approx(0.25)
    assert s.loc[24] == pytest.approx(0.25)
    assert math.isnan(s.loc[25]) and math.isnan(s.loc[30])
    at_risk = km.set_index("month")["at_risk"]
    assert at_risk.loc[0] == 5 and at_risk.loc[3] == 5 and at_risk.loc[4] == 4 and at_risk.loc[6] == 4
    assert at_risk.loc[12] == 3 and at_risk.loc[13] == 1 and at_risk.loc[25] == 0
    assert km.set_index("month")["events"].loc[[6, 12, 24]].tolist() == [1, 2, 0]
    assert survival.median_survival(km) == 12


def test_min_at_risk_truncates_the_tail():
    lt, _ = survival.lifetimes(frame(HAND), months(24))
    km = survival.kaplan_meier(lt, max_month=30, min_at_risk=3)
    s = km.set_index("month")["survival"]
    assert s.loc[12] == pytest.approx(0.25)     # 3 at risk at month 12: still reported
    assert math.isnan(s.loc[13])                # 1 at risk afterwards: not reported
    assert km.set_index("month")["at_risk"].loc[13] == 1   # but the count is still there


def test_completed_is_censored_not_an_event():
    rows = [dict(sheet_status="COMPLETED", actual_cod=months(10)),
            dict(sheet_status="COMPLETED"),                            # no actual_cod -> run date
            dict(sheet_status="WITHDRAWN", withdrawn_date=months(10))]
    lt, _ = survival.lifetimes(frame(rows), months(20))
    assert lt["event"].tolist() == [False, False, True]
    assert lt["t"].tolist() == [10, 20, 10]
    km = survival.kaplan_meier(lt, max_month=20, min_at_risk=1)
    s = km.set_index("month")["survival"]
    # month 10: 3 at risk, 1 withdrawal -> 2/3; the completed row leaves the risk set without an event
    assert s.loc[10] == pytest.approx(2 / 3)
    assert s.loc[20] == pytest.approx(2 / 3)
    assert km["events"].sum() == 1


def test_completed_after_run_date_is_censored_at_run_date():
    rows = [dict(sheet_status="COMPLETED", actual_cod=months(30))]
    lt, _ = survival.lifetimes(frame(rows), months(20))
    assert lt["t"].tolist() == [20]


def test_mw_weighting_differs_when_mw_differ():
    rows = [dict(sheet_status="WITHDRAWN", withdrawn_date=months(6), net_mw=900.0),
            dict(sheet_status="ACTIVE", net_mw=100.0),
            dict(sheet_status="ACTIVE", net_mw=100.0)]
    lt, _ = survival.lifetimes(frame(rows), months(12))
    km = survival.kaplan_meier(lt, max_month=12, min_at_risk=1).set_index("month")
    assert km.loc[6, "survival"] == pytest.approx(2 / 3)
    assert km.loc[6, "survival_mw_weighted"] == pytest.approx(200 / 1100)
    # equal MW -> weighted equals unweighted
    lt_eq, _ = survival.lifetimes(frame([{**r, "net_mw": 50.0} for r in rows]), months(12))
    km_eq = survival.kaplan_meier(lt_eq, max_month=12, min_at_risk=1)
    assert np.allclose(km_eq["survival"], km_eq["survival_mw_weighted"])


def test_exclusions_are_counted():
    rows = [dict(sheet_status="ACTIVE", queue_date=pd.NaT),
            dict(sheet_status="WITHDRAWN"),                                  # withdrawn, no date
            dict(sheet_status="WITHDRAWN", withdrawn_date=Q - pd.DateOffset(months=2)),   # before queue date
            dict(sheet_status="ACTIVE")]
    lt, excluded = survival.lifetimes(frame(rows), months(12))
    assert len(lt) == 1
    assert excluded == {"excluded_no_queue_date": 1, "excluded_withdrawn_no_date": 1, "excluded_end_before_queue": 1}


def test_cohorts_split_clusters_and_technology():
    pq = frame([dict(cluster="C13", is_standalone_storage=True, has_storage=True),
                dict(cluster="C14", has_solar=True, has_storage=True),
                dict(cluster="C14"),
                dict(cluster="C12")])
    c15 = frame([dict(cluster="C15", has_solar=True, has_storage=True)])
    cohorts = survival.build_cohorts(pq, c15)
    assert list(cohorts) == survival.CLUSTER_COHORTS + survival.TECH_COHORTS
    assert len(cohorts["C13"]) == 1 and len(cohorts["C14"]) == 2 and len(cohorts["C15"]) == 1
    assert len(cohorts["C13-C15 standalone storage"]) == 1
    assert len(cohorts["C13-C15 solar+storage"]) == 2
    assert len(cohorts["C13-C15 other"]) == 1
    assert len(cohorts["C10"]) == 0


def test_analyse_summary_and_long_shape():
    pq = frame(HAND)
    c15 = frame([{**r, "cluster": "C15"} for r in HAND])
    long_df, summary = survival.analyse(pq, c15, months(24), max_month=30, min_at_risk=1)
    assert set(long_df.columns) == {"cohort", "month", "at_risk", "events", "survival", "survival_mw_weighted"}
    assert (long_df.groupby("cohort").size() == 31).all()
    row = summary.set_index("cohort").loc["C13"]
    assert row["n"] == 5 and row["events"] == 3 and row["censored"] == 2
    assert row["s12"] == pytest.approx(0.25) and row["s24"] == pytest.approx(0.25)
    assert math.isnan(row["s36"])
    assert row["median_survival_months"] == 12
    assert row["follow_up_months"] == 24
    empty = summary.set_index("cohort").loc["C10"]
    assert empty["n"] == 0 and math.isnan(empty["s12"])


def test_render_svg_is_self_contained():
    pq = frame(HAND)
    long_df, _ = survival.analyse(pq, frame([]), months(24), max_month=30, min_at_risk=1)
    svg = survival.render_svg(long_df[long_df.cohort == "C13"])
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert svg.count("<polyline") == 1
    assert "C13" in svg and "months since queue date" in svg
    assert "http" not in svg.replace("http://www.w3.org/2000/svg", "")   # no external assets
    assert "prefers-color-scheme" in svg
    assert "prefers-color-scheme" not in survival.render_svg(long_df, adaptive=False)


def test_findings_use_withdrawal_not_failure():
    pq = frame(HAND + [{**r, "cluster": "C14", "net_mw": 50.0 * (i + 1)} for i, r in enumerate(HAND)])
    c15 = frame([{**r, "cluster": "C15"} for r in HAND])
    long_df, summary = survival.analyse(pq, c15, months(24), max_month=30, min_at_risk=1)
    text = survival.findings(summary)
    assert "withdraw" in text.lower()
    assert "fail" not in text.lower()
    assert "because" not in text.lower()
    assert text.count(". ") + 1 >= 6


# ----------------------------------------------- raw-day exclusion & C15 censoring

def test_withdrawal_days_before_the_queue_date_is_excluded_not_month_zero():
    """A withdrawal dated a few days BEFORE the queue date is a data error. Rounding to months
    turned it into a legitimate month-0 event, which is an immediate withdrawal that never happened."""
    rows = [dict(sheet_status="WITHDRAWN", withdrawn_date=Q - pd.Timedelta(days=5)),   # 5 days early
            dict(sheet_status="WITHDRAWN", withdrawn_date=Q - pd.Timedelta(days=1)),
            dict(sheet_status="WITHDRAWN", withdrawn_date=Q),                          # same day: kept, t=0
            dict(sheet_status="WITHDRAWN", withdrawn_date=Q + pd.Timedelta(days=5)),   # 5 days late: kept
            dict(sheet_status="ACTIVE")]
    lt, excluded = survival.lifetimes(frame(rows), months(24))
    assert excluded["excluded_end_before_queue"] == 2
    assert lt["t"].tolist() == [0, 0, 24]
    assert lt["event"].tolist() == [True, True, False]
    # the two excluded rows would each have rounded to month 0 and entered as events
    assert survival.months_between(pd.Series([Q]), pd.Series([Q - pd.Timedelta(days=5)])).tolist() == [0.0]


def test_completion_dated_before_the_queue_date_is_excluded_too():
    rows = [dict(sheet_status="COMPLETED", actual_cod=Q - pd.Timedelta(days=10)),
            dict(sheet_status="ACTIVE")]
    lt, excluded = survival.lifetimes(frame(rows), months(12))
    assert excluded["excluded_end_before_queue"] == 1
    assert len(lt) == 1 and not lt["event"].iloc[0]


def test_c15_cohort_is_censored_at_its_own_posting_date():
    """The C15 file cannot observe a withdrawal after it was posted; censoring its ACTIVE rows at
    the public report's later run date would publish structurally event-free months."""
    assert survival.C15_CENSOR_DATE == "2026-07-16"
    q = pd.Timestamp("2025-02-12")                      # the real C15 queue date
    rows = [dict(cluster="C15", sheet_status="ACTIVE", queue_date=q) for _ in range(6)]
    pq = frame([dict(cluster="C14", sheet_status="ACTIVE", queue_date=q)] * 6)
    long_df, summary = survival.analyse(pq, frame(rows), "2026-09-07", max_month=36, min_at_risk=1)
    s = summary.set_index("cohort")
    expected = int(survival.months_between(pd.Series([q]), pd.Series([pd.Timestamp(survival.C15_CENSOR_DATE)])).iloc[0])
    assert expected == 17
    # C15 stops at its posting date; C14, censored at the public run date, runs ~2 months longer
    c15_last = long_df[(long_df.cohort == "C15") & (long_df.at_risk > 0)].month.max()
    c14_last = long_df[(long_df.cohort == "C14") & (long_df.at_risk > 0)].month.max()
    assert c15_last == expected == 17
    assert c14_last == 19 and c14_last > c15_last
    assert s.loc["C15", "follow_up_months"] == 17


def test_c15_censor_date_does_not_touch_other_cohorts():
    q = pd.Timestamp("2025-02-12")
    rows = [dict(cluster=c, sheet_status="ACTIVE", queue_date=q) for c in ("C13", "C14")]
    lt13, _ = survival.lifetimes(frame([rows[0]]), "2026-09-07")
    lt15, _ = survival.lifetimes(frame([{**rows[0], "cluster": "C15"}]), survival.C15_CENSOR_DATE)
    assert lt13["t"].iloc[0] > lt15["t"].iloc[0]


# ------------------------------------------------------------------- real data

@pytest.mark.real_data
def test_real_data_smoke(real_projects):
    pq, c15 = real_projects
    run_date = str(pq["source_run_date"].iloc[0])
    long_df, summary = survival.analyse(pq, c15, run_date)
    cohorts = set(summary.cohort)
    assert {"C13", "C14", "C15"} <= cohorts
    s = summary.set_index("cohort")
    assert s.loc[["C13", "C14", "C15"], "n"].gt(50).all()
    assert s.loc["C15", "events"] > 0 and s.loc["C15", "censored"] > 0
    for c, g in long_df.groupby("cohort"):
        surv = g.sort_values("month")["survival"].dropna()
        if surv.empty:
            continue
        assert surv.between(0, 1).all(), c
        assert (np.diff(surv.to_numpy()) <= 1e-12).all(), f"{c} survival not monotone"
        mw = g.sort_values("month")["survival_mw_weighted"].dropna()
        assert mw.between(0, 1).all() and (np.diff(mw.to_numpy()) <= 1e-12).all(), c
        assert (g["at_risk"].diff().dropna() <= 0).all(), c
    assert (long_df.groupby("cohort")["month"].max() == survival.MAX_MONTH).all()
    assert "C15" in survival.render_svg(long_df[long_df.cohort.isin(survival.CLUSTER_COHORTS)])


@pytest.mark.real_data
def test_real_c15_follow_up_stops_at_its_posting_date(real_projects):
    """C15's real queue date is 2025-02-12; censoring at its own posting date gives 17 months of
    follow-up, not the 19 the public report's run date would imply (months 18-19 were structurally
    event-free because the C15 file could not observe them)."""
    pq, c15 = real_projects
    run_date = str(pq["source_run_date"].iloc[0])
    long_df, summary = survival.analyse(pq, c15, run_date)
    fu = int(summary.set_index("cohort").loc["C15", "follow_up_months"])
    at_run = survival.months_between(pd.Series([c15.queue_date.mode().iloc[0]]), pd.Series([pd.Timestamp(run_date)]))
    assert fu == 17
    assert int(at_run.iloc[0]) == 19 and fu < int(at_run.iloc[0])
    g = long_df[(long_df.cohort == "C15")]
    assert g[g.at_risk > 0].month.max() == 17
    assert g[g.month > 17].events.sum() == 0


@pytest.mark.real_data
def test_real_cohorts_have_no_end_before_queue_rows_left(real_projects):
    """The raw-day exclusion is what keeps a mis-dated withdrawal out of month 0. Whatever it
    excludes must not reappear as an event."""
    pq, c15 = real_projects
    _, summary = survival.analyse(pq, c15, str(pq["source_run_date"].iloc[0]))
    s = summary.set_index("cohort")
    assert (s["excluded_end_before_queue"] >= 0).all()
    assert (s["n"] == s["events"] + s["censored"]).all()


def test_regimes_cover_every_cluster_cohort_and_reach_chart_text_and_findings():
    """Every cluster cohort has a regime row; the legend carries the window year; C15 carries the footnote;
    the findings end with the regime caveat so the curves are never published without it."""
    assert set(survival.REGIMES) == set(survival.CLUSTER_COHORTS)
    for window, desc in survival.REGIMES.values():
        assert window[:4].isdigit() and len(desc) > 20
    assert survival.REGIMES["C15"][0] == "2025-02"                 # the file's queue date, not the 2023 window
    md = survival.regimes_markdown()
    assert "C14" in md and "2021-04" in md and "150 %" in md
    long_df = pd.DataFrame({"cohort": ["C13"] * 3 + ["C15"] * 3, "month": [0, 1, 2] * 2,
                            "survival": [1, .9, .8, 1, .95, .9], "at_risk": [10, 9, 8, 10, 9, 8]})
    svg = survival.render_svg(long_df)
    assert "C13 (2020)" in svg and "C15 (2025*)" in svg and "post-scoring queue date" in svg
    svg13 = survival.render_svg(long_df[long_df.cohort == "C13"])
    assert "post-scoring" not in svg13                              # footnote only when C15 is drawn
    assert survival.REGIME_CAVEAT.startswith("Attrition compares regimes")
