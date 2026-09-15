#!/usr/bin/env python3
"""
Queue-cohort survival analysis: how long do interconnection requests stay in the queue
before withdrawing, cluster by cluster.

    caiso-siting survival   ->  outputs/survival_by_cluster.csv, survival_summary.csv,
                                survival.svg, survival_tech.svg, survival.md

Cohorts
  C10 .. C14      `cluster` in the Public Queue Report
  C15             the Cluster 15 report
  C13-C15 x tech  C13, C14 and C15 combined, split into standalone storage
                  (`is_standalone_storage`), solar+storage hybrids (`has_solar & has_storage`)
                  and everything else

Time axis and events
  t      months since `queue_date`, rounded to the nearest whole month (days / 30.4375)
  event  withdrawal, at `withdrawn_date`
  censor ACTIVE rows at the Public Queue Report run date (`source_run_date`; Cluster 15 rows use
         C15's own posting date, C15_CENSOR_DATE, because the C15 file carries no run date and
         cannot observe a withdrawal after it was posted).
         COMPLETED rows are NOT events: completion is the success outcome. They are censored at
         `actual_cod` when present, else at the run date. This treats a completed project as
         "no longer at risk of withdrawal" from its commercial operation date on — a standard
         simplification (completion is really a competing outcome); it is documented, not hidden.
  excluded  rows with no `queue_date`, withdrawn rows with no `withdrawn_date`, and rows whose
            event/censor date precedes the queue date. Counts are reported per cohort.

Estimator
  Kaplan–Meier on a monthly grid 0..MAX_MONTH:  S(t) = prod_{u<=t} (1 - d_u / n_u)
  with n_u = projects whose t >= u (censored-at-u rows stay in the risk set at u) and d_u the
  withdrawals at month u. The MW-weighted variant replaces counts with sums of `net_mw`.
  S is NaN once fewer than MIN_AT_RISK projects remain at risk: a tail carried by a handful of rows
  (e.g. one C14 row whose queue date CAISO typed as 2011) is not reported. `at_risk` still shows it.

Nothing here says WHY anything withdrew. The CAISO files carry no reason beyond "IC Request".
"""
from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

from .config import OUT

CLUSTER_COHORTS = ["C10", "C11", "C12", "C13", "C14", "C15"]
# The Cluster 15 report carries no run date and its last observable withdrawal is dated 2026-07-14;
# censoring its ACTIVE rows at the public report's later run date would publish event-free months
# that the file could not have observed. Censor C15 at its posting date instead.
C15_CENSOR_DATE = "2026-07-16"


def c15_censor_date(c15: pd.DataFrame) -> str:
    """The posting date, or the latest withdrawal in the file if CAISO has re-posted since — an ACTIVE row can
    never be censored before an event the same file records."""
    if "withdrawn_date" in c15 and len(c15):
        latest = pd.to_datetime(c15["withdrawn_date"], errors="coerce", format="mixed").max()
        if pd.notna(latest) and latest.strftime("%Y-%m-%d") > C15_CENSOR_DATE:
            return latest.strftime("%Y-%m-%d")
    return C15_CENSOR_DATE
TECH_CLUSTERS = ["C13", "C14", "C15"]

# The process each cohort entered under. Attrition compares regimes, not only nodes: a cluster that had to
# prove site control and pay higher deposits to be in the queue at all will show a flatter curve for that
# reason alone. Window = the queue_date the CAISO file carries (C15's is the post-scoring date, see below).
# Sources: CAISO Cluster 15 intake scoring summary (2025-06-12); FERC order on CAISO's Cluster 14
# procedures (2021-09-24) as reported at the time; queue dates from the files themselves.
REGIMES = {
    "C10": ("2017-05", "standard cluster study process"),
    "C11": ("2018-04", "standard cluster study process"),
    "C12": ("2019-04", "standard cluster study process"),
    "C13": ("2020-04", "standard cluster study process"),
    "C14": ("2021-04", "373 requests / ~150 GW — 2.4x the prior year. Special FERC-approved procedures (Sept 2021): "
                       "Phase I cost estimates advisory only; full deposit refund on early withdrawal if Phase II costs "
                       "exceeded Phase I by 25 % or more; Phase I results delayed to Sept 2022."),
    "C15": ("2025-02", "First cluster scored under the 2023 IPE (commercial interest 30 %, viability 35 %, system "
                       "need 35 %) and capped at 150 % of available capacity per constraint. 541 requests / 347 GW "
                       "filed in the April 2023 window; 255 resubmitted Oct–Dec 2024; 145 / 68 GW proceeded to study "
                       "(CAISO, June 2025). The queue_date in the file is 2025-02-12, so month 0 here is AFTER that cut: "
                       "this cohort is already a filtered survivor set and its early months are not comparable to "
                       "C10–C14's. (The file holds 170 requests; CAISO's June 2025 summary counted 145 proceeding to "
                       "study — the difference is requests that withdrew during validation and are in the file as "
                       "withdrawn.)"),
}
REGIME_CAVEAT = ("Attrition compares regimes, not only nodes. C10–C13 entered under the standard cluster process; "
                 "C14 entered in April 2021 at 2.4x the prior year's volume under special procedures that made Phase I "
                 "cost estimates advisory and refunded deposits in full on early withdrawal when Phase II costs came in "
                 "25 % or more above Phase I; C15 is the first cohort scored and capped by zone under the 2023 IPE, and "
                 "its queue date (2025-02-12) is the post-scoring date, so the 541 → 170 intake cut happened before "
                 "its month 0. A flatter C14 or C15 curve is partly the rule change, not only the projects or the nodes.")
TECH_COHORTS = ["C13-C15 standalone storage", "C13-C15 solar+storage", "C13-C15 other"]
HORIZONS = (12, 24, 36, 48, 60)
MAX_MONTH = 120
MIN_AT_RISK = 5      # S(t) is reported only while at least this many projects remain at risk
DAYS_PER_MONTH = 30.4375

# Categorical palette validated (dataviz skill validator) against both the light and the dark
# surface: lightness band, chroma floor, CVD and normal-vision separation all pass; the yellow
# sits at 2.99:1 on light, which the direct line labels relieve.
PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"]


# ------------------------------------------------------------------ lifetimes

def months_between(start: pd.Series, end: pd.Series) -> pd.Series:
    """Whole months from start to end, rounded to the nearest month."""
    days = (pd.to_datetime(end) - pd.to_datetime(start)).dt.days
    return np.floor(days / DAYS_PER_MONTH + 0.5)


def lifetimes(df: pd.DataFrame, run_date: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, int]]:
    """One row per usable project: t (int months), event (bool), weight (net_mw, NaN -> 0).
    Returns the frame and the exclusion counts."""
    d = df.copy()
    run_date = pd.Timestamp(run_date)
    d["queue_date"] = pd.to_datetime(d["queue_date"], errors="coerce")
    wd = pd.to_datetime(d["withdrawn_date"], errors="coerce") if "withdrawn_date" in d \
        else pd.Series(pd.NaT, index=d.index)
    cod = pd.to_datetime(d["actual_cod"], errors="coerce") if "actual_cod" in d \
        else pd.Series(pd.NaT, index=d.index)
    status = d["sheet_status"].astype(str).str.upper()

    excluded = {"excluded_no_queue_date": int(d["queue_date"].isna().sum())}
    d = d[d["queue_date"].notna()]
    wd, cod, status = wd[d.index], cod[d.index], status[d.index]

    is_wd = status == "WITHDRAWN"
    excluded["excluded_withdrawn_no_date"] = int((is_wd & wd.isna()).sum())
    keep = ~(is_wd & wd.isna())
    d, wd, cod, status, is_wd = d[keep], wd[keep], cod[keep], status[keep], is_wd[keep]

    end = pd.Series(run_date, index=d.index)
    end = end.where(~is_wd, wd)
    done = (status == "COMPLETED") & cod.notna() & (cod <= run_date)
    end = end.where(~done, cod)

    # exclude on RAW days: months_between rounds, so a withdrawal dated a few days before the
    # queue date would otherwise round to month 0 and enter as a legitimate event
    bad = (pd.to_datetime(end) - pd.to_datetime(d["queue_date"])).dt.days < 0
    excluded["excluded_end_before_queue"] = int(bad.sum())
    d, end, is_wd = d[~bad], end[~bad], is_wd[~bad]
    t = months_between(d["queue_date"], end)
    bad = t < 0
    d, t, is_wd = d[~bad], t[~bad], is_wd[~bad]

    lt = pd.DataFrame({
        "t": t.astype(int),
        "event": is_wd.astype(bool),
        "weight": pd.to_numeric(d.get("net_mw", pd.Series(np.nan, index=d.index)), errors="coerce").fillna(0.0),
    }, index=d.index)
    return lt, excluded


# ------------------------------------------------------------------ cohorts

def build_cohorts(pq: pd.DataFrame, c15: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Cohort name -> project rows. Cluster cohorts C10..C15, then the C13–C15 technology split."""
    both = pd.concat([pq, c15], ignore_index=True, sort=False)
    both["cluster"] = both["cluster"].astype(str).str.upper().str.strip()
    cohorts: dict[str, pd.DataFrame] = {}
    for c in CLUSTER_COHORTS:
        cohorts[c] = both[both["cluster"] == c]
    tech = both[both["cluster"].isin(TECH_CLUSTERS)]
    sto = tech["is_standalone_storage"].fillna(False).astype(bool)
    hyb = tech["has_solar"].fillna(False).astype(bool) & tech["has_storage"].fillna(False).astype(bool) & ~sto
    cohorts[TECH_COHORTS[0]] = tech[sto]
    cohorts[TECH_COHORTS[1]] = tech[hyb]
    cohorts[TECH_COHORTS[2]] = tech[~sto & ~hyb]
    return cohorts


# ------------------------------------------------------------------ Kaplan–Meier

def kaplan_meier(lt: pd.DataFrame, max_month: int = MAX_MONTH, min_at_risk: int = MIN_AT_RISK) -> pd.DataFrame:
    """Monthly-grid KM: month, at_risk, events, survival, survival_mw_weighted. Survival columns are
    NaN from the first month with fewer than `min_at_risk` projects at risk."""
    t = lt["t"].to_numpy(dtype=int)
    e = lt["event"].to_numpy(dtype=bool)
    w = lt["weight"].to_numpy(dtype=float)
    s, s_w = 1.0, 1.0
    rows = []
    for m in range(max_month + 1):
        risk = t >= m
        n = int(risk.sum())
        ev = risk & e & (t == m)
        d = int(ev.sum())
        if n < max(1, min_at_risk):
            rows.append((m, n, d, np.nan, np.nan))
            continue
        s *= 1.0 - d / n
        n_w = float(w[risk].sum())
        if n_w > 0:
            s_w *= 1.0 - float(w[ev].sum()) / n_w
        rows.append((m, n, d, s, s_w))
    return pd.DataFrame(rows, columns=["month", "at_risk", "events", "survival", "survival_mw_weighted"])


def _s_at(km: pd.DataFrame, month: int, col: str = "survival") -> float:
    hit = km.loc[km["month"] == month, col]
    return float(hit.iloc[0]) if len(hit) else float("nan")


def median_survival(km: pd.DataFrame) -> float:
    below = km[km["survival"].notna() & (km["survival"] <= 0.5)]
    return float(below["month"].iloc[0]) if len(below) else float("nan")


def summarize(cohort: str, lt: pd.DataFrame, km: pd.DataFrame, excluded: dict[str, int]) -> dict:
    row = {
        "cohort": cohort,
        "n": int(len(lt)),
        "events": int(lt["event"].sum()),
        "censored": int((~lt["event"]).sum()),
        "mw_total": round(float(lt["weight"].sum()), 1),
        "mw_withdrawn": round(float(lt.loc[lt["event"], "weight"].sum()), 1),
        "follow_up_months": int(km.loc[km["survival"].notna(), "month"].max()) if km["survival"].notna().any() else 0,
        "median_survival_months": median_survival(km),
    }
    for h in HORIZONS:
        row[f"s{h}"] = round(_s_at(km, h), 4)
    for h in HORIZONS:
        row[f"s{h}_mw"] = round(_s_at(km, h, "survival_mw_weighted"), 4)
    row.update(excluded)
    return row


def analyse(pq: pd.DataFrame, c15: pd.DataFrame, run_date, max_month: int = MAX_MONTH,
            min_at_risk: int = MIN_AT_RISK) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(long survival table, one-row-per-cohort summary)."""
    long_parts, summary_rows = [], []
    c15_censor = c15_censor_date(c15)
    for name, rows in build_cohorts(pq, c15).items():
        cohort_run = c15_censor if name == "C15" else run_date
        lt, excluded = lifetimes(rows, cohort_run)
        km = kaplan_meier(lt, max_month, min_at_risk)
        km.insert(0, "cohort", name)
        long_parts.append(km)
        summary_rows.append(summarize(name, lt, km, excluded))
    return pd.concat(long_parts, ignore_index=True), pd.DataFrame(summary_rows)


# ------------------------------------------------------------------ chart

def _fmt_num(v: float) -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.2f}"


def render_svg(long_df: pd.DataFrame, title: str = "Share of projects not yet withdrawn, by months since queue date",
               width: int = 700, height: int = 360, adaptive: bool = True) -> str:
    """Inline SVG line chart of `survival` per cohort. No external assets. Text and axes use
    currentColor; with `adaptive` the file carries a prefers-color-scheme rule so the standalone
    .svg reads on light and dark backgrounds (pass adaptive=False when inlining into a page that
    sets its own colour). Series colours are PALETTE."""
    cohorts = list(dict.fromkeys(long_df["cohort"]))
    # direct labels drop a prefix every cohort shares ("C13-C15 ") — the title carries it
    prefix = "C13-C15 " if cohorts and all(c.startswith("C13-C15 ") for c in cohorts) else ""
    short = {c: c[len(prefix):] for c in cohorts}
    label_chars = max([len(v) for v in short.values()] + [3]) + len(" 0.00 @ 120m")
    foot = 28 if "C15" in cohorts else 0          # two footnote lines under the axis label (regime caveat)
    ml, mr, mt, mb = 48, min(270, 18 + int(7.0 * label_chars)), 48, 40 + foot
    pw, ph = width - ml - mr, height - mt - mb
    max_x = int(long_df.loc[long_df["survival"].notna(), "month"].max()) if long_df["survival"].notna().any() else MAX_MONTH
    max_x = max(12, math.ceil(max_x / 12) * 12)

    def x(m: float) -> float:
        return ml + pw * m / max_x

    def y(s: float) -> float:
        return mt + ph * (1 - s)

    font = 'font-family="system-ui,-apple-system,Segoe UI,Roboto,sans-serif"'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           f'role="img" aria-label="{title}" {font} font-size="12" fill="currentColor">',
           f'<title>{title}</title>']
    if adaptive:
        out.append('<style>svg{color:#2a2a28}@media (prefers-color-scheme: dark){svg{color:#d8d8d2}}</style>')
    out += [f'<text x="{ml}" y="18" font-size="13" font-weight="600">{title}</text>']
    # gridlines + y axis labels
    for k in range(0, 11, 2):
        s = k / 10
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{y(s):.1f}" y2="{y(s):.1f}" stroke="currentColor" '
                   f'stroke-opacity="0.15" stroke-width="1"/>')
        out.append(f'<text x="{ml - 6}" y="{y(s) + 4:.1f}" text-anchor="end" fill-opacity="0.75">{s:.1f}</text>')
    # x ticks every 12 months
    for m in range(0, max_x + 1, 12):
        out.append(f'<line x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{mt + ph}" y2="{mt + ph + 4}" stroke="currentColor" '
                   f'stroke-opacity="0.6"/>')
        out.append(f'<text x="{x(m):.1f}" y="{mt + ph + 16}" text-anchor="middle" fill-opacity="0.75">{m}</text>')
    out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}" stroke="currentColor" stroke-opacity="0.6"/>')
    out.append(f'<line x1="{ml}" x2="{ml}" y1="{mt}" y2="{mt + ph}" stroke="currentColor" stroke-opacity="0.6"/>')
    out.append(f'<text x="{ml + pw / 2:.1f}" y="{height - foot - 8}" text-anchor="middle" fill-opacity="0.75">months since queue date</text>')
    out.append(f'<text transform="translate(12,{mt + ph / 2:.1f}) rotate(-90)" text-anchor="middle" fill-opacity="0.75">S(t)</text>')
    # series
    label_slots: list[tuple[float, str, str]] = []
    for i, c in enumerate(cohorts):
        col = PALETTE[i % len(PALETTE)]
        g = long_df[(long_df["cohort"] == c) & long_df["survival"].notna()].sort_values("month")
        if g.empty:
            continue
        pts = []
        prev = None
        for m, s in zip(g["month"], g["survival"], strict=True):
            if prev is not None:
                pts.append(f"{x(m):.1f},{y(prev):.1f}")     # step: hold the previous value up to m
            pts.append(f"{x(m):.1f},{y(s):.1f}")
            prev = s
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{col}" stroke-width="2" '
                   f'stroke-linejoin="round"><title>{c}</title></polyline>')
        last_m, last_s = float(g["month"].iloc[-1]), float(g["survival"].iloc[-1])
        label_slots.append((y(last_s), f"{short[c]} {last_s:.2f} @ {int(last_m)}m", col))
    # direct labels at line ends, nudged apart so they never overlap
    label_slots.sort(key=lambda r: r[0])
    placed: list[float] = []
    for yy, txt, col in label_slots:
        if placed and yy - placed[-1] < 14:
            yy = placed[-1] + 14
        placed.append(yy)
        out.append(f'<circle cx="{ml + pw + 4}" cy="{yy:.1f}" r="4" fill="{col}"/>')
        out.append(f'<text x="{ml + pw + 12}" y="{yy + 4:.1f}" fill-opacity="0.9">{txt}</text>')
    # legend
    lx = ml
    for i, c in enumerate(cohorts):
        col = PALETTE[i % len(PALETTE)]
        lbl = f"{c} ({REGIMES[c][0][:4]}{'*' if c == 'C15' else ''})" if c in REGIMES else c
        out.append(f'<rect x="{lx}" y="{mt - 18}" width="14" height="3" fill="{col}"/>')
        out.append(f'<text x="{lx + 18}" y="{mt - 13}" font-size="11" fill-opacity="0.85">{lbl}</text>')
        lx += 26 + 6.5 * len(lbl)
    if foot:
        out.append(f'<text x="{ml}" y="{height - 18}" font-size="10" fill-opacity="0.7">* C15 month 0 is its '
                   f'post-scoring queue date (2025-02); the 2023 intake cut (541 → 170 requests) precedes it.</text>')
        out.append(f'<text x="{ml}" y="{height - 6}" font-size="10" fill-opacity="0.7">Curves compare process '
                   f'regimes, not only nodes — see the regime table.</text>')
    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------ findings

def findings(summary: pd.DataFrame) -> str:
    """Six plain sentences computed from the summary. Withdrawal, never failure; never a cause."""
    s = summary.set_index("cohort")
    clus = s.loc[[c for c in CLUSTER_COHORTS if c in s.index]]
    with24 = clus[clus["s24"].notna()]
    steep = with24["s24"].idxmin()
    shallow = with24["s24"].idxmax()
    out = [
        f"Among cluster cohorts with at least 24 months of follow-up, {steep} shows the steepest 24-month attrition: "
        f"{1 - with24.loc[steep, 's24']:.0%} of its {int(with24.loc[steep, 'n'])} projects had withdrawn by month 24, "
        f"against {1 - with24.loc[shallow, 's24']:.0%} for {shallow}, the shallowest.",
    ]
    if "C15" in s.index:
        c15 = s.loc["C15"]
        fu = int(c15["follow_up_months"])
        out.append(f"Cluster 15 has {fu} months of follow-up so far; at month 12 its unweighted S is "
                   f"{_fmt_num(c15['s12'])} and its MW-weighted S is {_fmt_num(c15['s12_mw'])}, "
                   f"versus S(12) of {_fmt_num(s.loc['C14', 's12']) if 'C14' in s.index else 'n/a'} for C14 and "
                   f"{_fmt_num(s.loc['C13', 's12']) if 'C13' in s.index else 'n/a'} for C13 at the same age.")
    reached = clus[clus["median_survival_months"].notna()]
    not_reached = clus[clus["median_survival_months"].isna()]
    if len(reached):
        parts = ", ".join(f"{c} at month {int(m)}" for c, m in reached["median_survival_months"].items())
        out.append(f"Median time to withdrawal is reached for {parts}"
                   + (f"; {', '.join(not_reached.index)} " + ("has" if len(not_reached) == 1 else "have")
                      + " not yet crossed S = 0.5 within " + ("its" if len(not_reached) == 1 else "their")
                      + " follow-up." if len(not_reached) else "."))
    else:
        out.append("No cluster cohort has yet crossed S = 0.5 within its follow-up.")
    if "C14" in s.index and not math.isnan(s.loc["C14", "s24"]):
        u, w = s.loc["C14", "s24"], s.loc["C14", "s24_mw"]
        rel = "larger" if w < u else "smaller"
        out.append(f"For C14 the MW-weighted S(24) of {w:.2f} is {'below' if w < u else 'at or above'} the unweighted "
                   f"{u:.2f}, so the projects that withdrew in the first two years were on average {rel} than those "
                   f"that stayed.")
    tech = s.loc[[c for c in TECH_COHORTS if c in s.index]]
    h = 24 if tech["s24"].notna().all() else 12
    lo, hi = tech[f"s{h}"].idxmin(), tech[f"s{h}"].idxmax()
    out.append(f"Within C13–C15 by technology, {lo.replace('C13-C15 ', '')} has the lowest S({h}) at "
               f"{tech.loc[lo, f's{h}']:.2f} and {hi.replace('C13-C15 ', '')} the highest at {tech.loc[hi, f's{h}']:.2f} "
               f"(n = {int(tech.loc[lo, 'n'])} and {int(tech.loc[hi, 'n'])}).")
    excl = int(summary[["excluded_no_queue_date", "excluded_withdrawn_no_date", "excluded_end_before_queue"]]
               .loc[summary["cohort"].isin(CLUSTER_COHORTS)].sum().sum())
    comp = int((clus["censored"]).sum())
    out.append(f"Across the six cluster cohorts {int(clus['n'].sum())} projects enter the analysis, "
               f"{int(clus['events'].sum())} withdrawals are events, {comp} rows are censored (active at the report run "
               f"date or completed at their on-line date — completion is success, not an event), and {excl} rows were "
               f"excluded for missing or inconsistent dates.")
    out.append(REGIME_CAVEAT)
    return " ".join(out)


def summary_markdown(summary: pd.DataFrame) -> str:
    cols = ["cohort", "n", "events", "censored", "mw_total", "follow_up_months", "median_survival_months",
            "s12", "s24", "s36", "s48", "s60", "s12_mw", "s24_mw", "s36_mw", "s48_mw", "s60_mw"]
    d = summary[cols].copy()
    for c in cols[7:]:
        d[c] = d[c].map(_fmt_num)
    d["median_survival_months"] = d["median_survival_months"].map(lambda v: "not reached" if math.isnan(v) else f"{v:.0f}")
    d["mw_total"] = d["mw_total"].map(lambda v: f"{v:,.0f}")
    return d.to_markdown(index=False, colalign=("left",) + ("right",) * (len(cols) - 1), disable_numparse=True)


def regimes_markdown() -> str:
    rows = [{"cohort": c, "queue window": w, "process the cohort entered under": d} for c, (w, d) in REGIMES.items()]
    return pd.DataFrame(rows).to_markdown(index=False)


def write_markdown(summary: pd.DataFrame, run_date: str, text: str, c15_censor: str = C15_CENSOR_DATE) -> str:
    return f"""# Queue-cohort survival — Kaplan–Meier by cluster

Source: CAISO Public Queue Report (run date {run_date}) for C10–C14; CAISO Cluster 15 report for C15,
censored at {c15_censor} (its posting date, or the latest withdrawal the file records if CAISO has re-posted since) —
that file cannot record a withdrawal after it was published.
Event = withdrawal at `withdrawn_date`. ACTIVE rows are censored at the report run date; COMPLETED rows are
censored at `actual_cod` (completion is success, not an event). Time = months since `queue_date`.
`s12`…`s60` = Kaplan–Meier S(t) at 12…60 months; `_mw` = the same estimate with each project weighted by `net_mw`.
n/a = the cohort has not been observed that long with at least {MIN_AT_RISK} projects still at risk (`follow_up_months`
is the last month that holds). No figure states a cause; the CAISO files carry none.

![Kaplan–Meier survival by cluster](survival.svg)

![Kaplan–Meier survival, C13–C15 by technology](survival_tech.svg)

## Summary

{summary_markdown(summary)}

## Findings

{text}

## Process regime by cohort

{regimes_markdown()}

Full monthly table: `survival_by_cluster.csv`. Definitions: `DATA.md`.
"""


# ------------------------------------------------------------------ main

def main() -> None:
    from .nodes import load_projects
    pq, c15 = load_projects()
    run_date = str(pq["source_run_date"].iloc[0]) if "source_run_date" in pq and len(pq) else ""
    if not run_date:
        run_date = pd.Timestamp.today().strftime("%Y-%m-%d")
        print(f"warning: public report carries no run date; censoring at today ({run_date})", file=sys.stderr)
    long_df, summary = analyse(pq, c15, run_date)
    OUT.mkdir(exist_ok=True)
    long_df.to_csv(OUT / "survival_by_cluster.csv", index=False)
    summary.to_csv(OUT / "survival_summary.csv", index=False)
    (OUT / "survival.svg").write_text(render_svg(long_df[long_df["cohort"].isin(CLUSTER_COHORTS)]), encoding="utf-8")
    (OUT / "survival_tech.svg").write_text(
        render_svg(long_df[long_df["cohort"].isin(TECH_COHORTS)],
                   title="C13–C15 by technology: share not yet withdrawn"), encoding="utf-8")
    text = findings(summary)
    (OUT / "survival.md").write_text(write_markdown(summary, run_date, text, c15_censor_date(c15)), encoding="utf-8")
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print(summary[["cohort", "n", "events", "censored", "follow_up_months", "median_survival_months",
                   "s12", "s24", "s36", "s60", "s24_mw"]].to_string(index=False))
    print("\n" + text)
    print("\nwrote outputs/survival_by_cluster.csv, survival_summary.csv, survival.svg, survival_tech.svg, survival.md")


if __name__ == "__main__":
    main()
