"""site.py: the node page reads as seven questions, dims ratios with too few projects behind them, marks what is
not public, and the methodology page states every metric."""
from __future__ import annotations

import pandas as pd

from caiso_siting import site

PROV = dict(run_date="2026-09-14", commit="abc123", run="2026-09-14T00:00:00Z", built="2026-09-14T00:00:01Z")


def node(**kw) -> pd.Series:
    base = dict(node_key="VIEJO", poi_base="VIEJO", county="ORANGE", utility="SCE", state="CA",
                legacy_active_mw=300.0, legacy_active_projects=1, c15_active_mw=0.0, c15_active_projects=0,
                operating_mw=0.0, operating_projects=0, committed_mw=300.0, committed_projects=1,
                c15_fcds_req_mw=0.0, p2_reached_mw=300.0, p2_withdrawn_mw=0.0, p2_withdrawn_projects=0,
                p2_attrition=0.0, p2_n=1, tpd25_req_mw=300.0, tpd25_alloc_mw=300.0, tpd25_projects=1,
                tpd25_denied_ppa_mw=0.0, tpd25_denied_D_mw=0.0, tpd24_fcdsa_projects=1, tpd24_pcdsa_projects=0,
                lcr_status="", lcr_area="", lcr_sub_area="", lcr_note="", lcr_source="",
                wd_recent_mw=1000.0, wd_recent_projects=1, wd_recent_storage_mw=1000.0, storage_churn=3.33,
                churn_n=2, c15_survival=0.0, c15_n=1, c15_withdrawn_mw=1000.0, pipeline_storage_mw=300.0,
                operating_storage_mw=0.0, wd_alltime_mw=1000.0, wd_alltime_projects=1, c16_poi_status="",
                c16_poi_note="", geo_method="exact", geo_score=1.0, osm_name="Viejo", lat=33.6, lon=-117.7)
    base.update(kw)
    return pd.Series(base)


PROJECTS = pd.DataFrame([
    dict(node_key="VIEJO", project_name="TYRELL", queue_position="2125", sheet_status="ACTIVE", cluster="C14",
         net_mw=300.0, storage_mw=300.0, deliverability="FULL CAPACITY", ia_status="EXECUTED", cod="2032-05-26",
         withdrawn_date="", report="PUBLIC"),
    dict(node_key="VIEJO", project_name="CRUSADE", queue_position="2350", sheet_status="WITHDRAWN", cluster="C15",
         net_mw=1000.0, storage_mw=1000.0, deliverability="FULL CAPACITY (REQ)", ia_status="", cod="",
         withdrawn_date="2026-07-14", report="C15"),
])


def test_node_page_has_seven_questions_in_order_and_dims_small_n():
    html = site.node_page(node(), PROJECTS, PROV)
    qs = ["Can you get in?", "Who is ahead of you?", "Do projects leave after seeing the costs?",
          "Will you be deliverable?", "Will the power be worth anything here?", "Will the land pass intake?",
          "How long, and who gave up?"]
    pos = [html.index(q) for q in qs]
    assert pos == sorted(pos)
    assert html.count("<b>Not public:</b>") >= 4
    assert "3.33" in html and 'class="fact dim"' in html          # the Viejo ratio is shown, and dimmed
    assert "(n=2)" in html
    assert "2032-05-26" in html and "2032-05-26 to 2032-05-26" not in html
    assert "methodology.html" in html


def test_node_page_does_not_dim_a_well_supported_ratio():
    html = site.node_page(node(storage_churn=0.09, churn_n=33, pipeline_storage_mw=3000.0, c15_survival=1.0,
                               c15_n=3, c15_active_mw=801.0, c15_withdrawn_mw=0.0, p2_attrition=0.23, p2_n=35,
                               p2_reached_mw=5954.0), PROJECTS, PROV)
    assert 'class="fact dim"' not in html
    assert "0.09" in html and "(n=33)" in html


def test_node_page_lcr_in_and_outside_render_differently():
    inside = site.node_page(node(lcr_status="in LA Basin", lcr_area="LA Basin", lcr_source="LCT [2026-04-29]"),
                            PROJECTS, PROV)
    outside = site.node_page(node(lcr_status="outside LA Basin", lcr_note="Lugo is out", lcr_source="LCT"),
                             PROJECTS, PROV)
    assert "Local Capacity Area: LA Basin" in inside and 'class="ok"' in inside
    assert "Outside LA Basin local area boundary" in outside and "Lugo is out" in outside


def test_node_page_escapes_hostile_source_text():
    html = site.node_page(node(poi_base='<script>alert(1)</script>', lcr_status="in X", lcr_area="<b>X</b>",
                               lcr_source="s", c16_poi_status="AVAILABLE", c16_poi_note="<img src=x>"),
                          PROJECTS, PROV)
    assert "<script>alert(1)</script>" not in html and "<img src=x>" not in html and "<b>X</b>" not in html


def test_methodology_page_lists_every_metric_and_the_not_public_list():
    html = site.methodology_page(PROV)
    for m, _ in site.METRIC_DEFS:
        assert f"<code>{m}</code>" in html, m
    for what, _ in site.NOT_PUBLIC:
        assert what in html
    assert "Attrition compares regimes" in html and "No composite score" in html
    assert str(site.MIN_N) in html and f"{site.MIN_DENOM_MW:,}" in html
