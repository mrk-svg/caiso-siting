"""oasis.py: PRC_LMP parsing, TB4 daily/monthly/summary metrics, PNode suggestion, mapping-file
protections (confirmed rows never overwritten, unconfirmed rows never queried), cache, CLI wiring.
No network: every downloader is a fake."""
from __future__ import annotations

import inspect
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from caiso_siting import cli, nodes, oasis

# ------------------------------------------------------------------- fixtures

# Hand-written CSV in OASIS's PRC_LMP layout (resultformat=6). Two operating days, four LMP_TYPE rows
# per hour for the first two hours to prove the filter keeps only LMP (the total), plus a duplicate row.
PRC_LMP_HEADER = ("INTERVALSTARTTIME_GMT,INTERVALENDTIME_GMT,OPR_DT,OPR_HR,OPR_INTERVAL,NODE_ID_XML,NODE_ID,NODE,"
                  "MARKET_RUN_ID,LMP_TYPE,XML_DATA_ITEM,PNODE_RESMB,GRP_TYPE,POS,MW,GROUP")


def prc_lmp_csv(prices_by_day: dict[str, list[float]], node: str = "TESTNODE_2_N001") -> str:
    lines = [PRC_LMP_HEADER]
    for day, prices in prices_by_day.items():
        d = pd.Timestamp(day)
        for i, p in enumerate(prices, start=1):
            start = d + pd.Timedelta(hours=i - 1 + 8)   # GMT = local PST + 8
            end = start + pd.Timedelta(hours=1)
            base = (f"{start:%Y-%m-%dT%H:%M:00-00:00},{end:%Y-%m-%dT%H:%M:00-00:00},{day},{i},0,"
                    f"{node},{node},{node},DAM")
            lines.append(f"{base},LMP,LMP_PRC,{node},ALL,{i},{p},1")
            if i <= 2:
                lines.append(f"{base},MCE,LMP_ENE_PRC,{node},ALL,{i},{p - 1},1")
                lines.append(f"{base},MCC,LMP_CONG_PRC,{node},ALL,{i},1.5,1")
                lines.append(f"{base},MCL,LMP_LOSS_PRC,{node},ALL,{i},-0.5,1")
    lines.append(lines[1])   # OASIS occasionally repeats a row across windows
    return "\n".join(lines) + "\n"


DAY1 = [20, 18, 15, 12, 14, 16, 25, 30, 35, 40, 38, 36, 34, 30, 28, 33, 45, 80, 120, 110, 90, 60, 40, 25]
DAY2 = [30] * 24


@pytest.fixture
def csv_two_days() -> str:
    return prc_lmp_csv({"2026-01-05": DAY1, "2026-01-06": DAY2})


def pnodes_frame(names) -> pd.DataFrame:
    return pd.DataFrame({"PNODE_ID": names, "PNODE_TYPE": ["N"] * len(names),
                         "START_DATE_GMT": ["2000-01-01T08:00:00-00:00"] * len(names),
                         "END_DATE_GMT": ["2099-01-01T08:00:00-00:00"] * len(names)})


PNODES = ["WINDHUB_2_N001", "WINDHUB_7_N005", "REDBLUF_2_N101", "VINCENT_2_N001", "VINCNT_7_B1",
          "WHIRLWD_2_N001", "MOSSLND_2_N010", "CROWSLD_1_N001", "ROSSLND_6_N010", "EASTCITY_1_N001", "GATES_2_N001"]


# ------------------------------------------------------------------- parse_prc_lmp

def test_parse_prc_lmp_keeps_only_lmp_total(csv_two_days):
    h = oasis.parse_prc_lmp(csv_two_days)
    assert list(h.columns) == ["ts", "lmp", "node"]
    assert len(h) == 48                                   # 2 days × 24 hours, MCE/MCC/MCL and the duplicate dropped
    assert h.ts.dt.tz is None
    assert h.ts.iloc[0] == pd.Timestamp("2026-01-05 00:00")
    assert h.ts.iloc[23] == pd.Timestamp("2026-01-05 23:00")
    assert h.lmp.iloc[0] == 20 and h.lmp.iloc[18] == 120 # the LMP row, not the MCE row (19)
    assert h.ts.is_monotonic_increasing and h.ts.is_unique
    assert (h.node == "TESTNODE_2_N001").all()


def test_parse_prc_lmp_falls_back_to_gmt_when_opr_columns_missing():
    text = ("INTERVALSTARTTIME_GMT,INTERVALENDTIME_GMT,NODE,MARKET_RUN_ID,LMP_TYPE,MW\n"
            "2026-07-01T07:00:00-00:00,2026-07-01T08:00:00-00:00,X,DAM,LMP,12.5\n"
            "2026-07-01T08:00:00-00:00,2026-07-01T09:00:00-00:00,X,DAM,MCC,1\n")
    h = oasis.parse_prc_lmp(text)
    assert len(h) == 1 and h.ts.iloc[0] == pd.Timestamp("2026-07-01 00:00") and h.lmp.iloc[0] == 12.5   # PDT


def test_parse_prc_lmp_without_price_column_raises():
    with pytest.raises(ValueError):
        oasis.parse_prc_lmp("OPR_DT,OPR_HR,LMP_TYPE\n2026-01-01,1,LMP\n")


# ------------------------------------------------------------------- tb4_daily

def hourly(prices_by_day: dict[str, list[float]]) -> pd.DataFrame:
    rows = [(pd.Timestamp(d) + pd.Timedelta(hours=i), p) for d, ps in prices_by_day.items() for i, p in enumerate(ps)]
    return pd.DataFrame(rows, columns=["ts", "lmp"])


def test_tb4_daily_is_top4_mean_minus_bottom4_mean():
    d = oasis.tb4_daily(hourly({"2026-01-05": DAY1, "2026-01-06": DAY2}))
    assert list(d.columns) == ["date", "hours", "lmp_mean", "top4", "bottom4", "tb4"]
    r = d.set_index("date").loc[pd.Timestamp("2026-01-05")]
    assert r.hours == 24
    assert r.top4 == pytest.approx(np.mean([120, 110, 90, 80]))
    assert r.bottom4 == pytest.approx(np.mean([12, 14, 15, 16]))
    assert r.tb4 == pytest.approx(100 - 14.25)
    assert r.lmp_mean == pytest.approx(np.mean(DAY1), abs=0.01)
    flat = d.set_index("date").loc[pd.Timestamp("2026-01-06")]
    assert flat.tb4 == 0 and flat.lmp_mean == 30


def test_tb4_daily_drops_short_days_and_nans():
    h = hourly({"2026-01-05": DAY1, "2026-02-01": [5, 50, 7]})   # a 3-hour spill-over day
    h.loc[3, "lmp"] = np.nan
    d = oasis.tb4_daily(h)
    assert d.date.tolist() == [pd.Timestamp("2026-01-05")]
    assert d.hours.iloc[0] == 23
    assert oasis.tb4_daily(h.iloc[0:0]).empty


def test_tb4_daily_negative_prices():
    prices = [-20, -10, 0, 5] + [10] * 16 + [60, 70, 80, 90]
    d = oasis.tb4_daily(hourly({"2026-04-01": prices}))
    assert d.tb4.iloc[0] == pytest.approx(75 - (-6.25))


# ------------------------------------------------------------------- monthly / summarise

def daily_frame() -> pd.DataFrame:
    days = pd.date_range("2026-01-01", "2026-02-28", freq="D")
    a = pd.DataFrame({"node_key": "WINDHUB", "pnode": "WINDHUB_2_N001", "date": days,
                      "hours": 24, "lmp_mean": 40.0, "top4": 100.0, "bottom4": 20.0, "tb4": 80.0})
    a.loc[a.date.dt.month == 2, "tb4"] = 40.0
    b = pd.DataFrame({"node_key": "VINCENT", "pnode": "VINCENT_2_N001", "date": days[:31],
                      "hours": 24, "lmp_mean": 35.0, "top4": 60.0, "bottom4": 10.0,
                      "tb4": np.linspace(0, 100, 31)})
    return pd.concat([a, b], ignore_index=True)


def test_monthly_columns_and_values():
    m = oasis.monthly(daily_frame())
    assert list(m.columns) == ["node_key", "pnode", "month", "days", "tb4_mean", "tb4_p90", "lmp_mean"]
    w = m[m.node_key == "WINDHUB"].set_index("month")
    assert w.days.tolist() == [31, 28]
    assert w.tb4_mean.tolist() == [80.0, 40.0] and w.tb4_p90.tolist() == [80.0, 40.0]
    v = m[m.node_key == "VINCENT"].iloc[0]
    assert v.month == "2026-01" and v.tb4_mean == 50.0 and v.tb4_p90 == 90.0 and v.lmp_mean == 35.0
    assert oasis.monthly(daily_frame().iloc[0:0]).empty


def test_summarise_over_all_days():
    s = oasis.summarise(daily_frame())
    assert list(s.columns) == ["node_key", "pnode", "months", "tb4_12mo_mean", "tb4_12mo_p90", "lmp_12mo_mean",
                               "first_month", "last_month"]
    w = s.set_index("node_key").loc["WINDHUB"]
    assert w.months == 2 and w.first_month == "2026-01" and w.last_month == "2026-02"
    assert w.tb4_12mo_mean == pytest.approx((31 * 80 + 28 * 40) / 59, abs=0.01)
    assert w.tb4_12mo_p90 == 80.0 and w.lmp_12mo_mean == 40.0
    v = s.set_index("node_key").loc["VINCENT"]
    assert v.months == 1 and v.tb4_12mo_mean == 50.0 and v.tb4_12mo_p90 == 90.0
    assert s.node_key.tolist() == ["WINDHUB", "VINCENT"]      # sorted by tb4 mean, best first
    assert oasis.summarise(daily_frame().iloc[0:0]).empty


# ------------------------------------------------------------------- suggest / match

def test_match_pnode_first_token_rule():
    best, score, alts = oasis.match_pnode("WINDHUB", PNODES)
    assert best == "WINDHUB_2_N001" and score == 1.0 and alts == ["WINDHUB_7_N005"]
    best, score, _ = oasis.match_pnode("WHIRLWIND", PNODES)
    assert best == "WHIRLWD_2_N001" and score >= 0.85
    # MOSS LANDING must not land on ROSSLND / CROWSLD even when the ratio is high
    assert oasis.match_pnode("MOSS LANDING", ["ROSSLND_6_N010", "CROWSLD_1_N001"])[0] is None
    assert oasis.match_pnode("EAST COUNTY", PNODES)[0] is None
    assert oasis.match_pnode("", PNODES) == (None, 0.0, [])


def test_suggest_writes_unconfirmed_candidates_and_keeps_confirmed_rows():
    nodes_df = pd.DataFrame({"node_key": ["WINDHUB", "RED BLUFF", "VINCENT", "DELANEY COLORADO RIVER", "GATES"],
                             "pipeline_mw": [4600, 3592, 3520, 3200, 100]})
    mapping = pd.DataFrame([
        dict(node_key="VINCENT", pnode="HAND_PICKED_2_N001", confirmed="yes", note="confirmed by hand"),
        dict(node_key="WINDHUB", pnode="", confirmed="no", note="fill from data/pnodes.csv"),
        dict(node_key="OLD NODE", pnode="OLDNODE_2_N001", confirmed="no", note="stale suggestion"),
    ])
    out = oasis.suggest(nodes_df, pnodes_frame(PNODES), mapping, top_n=4)
    assert list(out.columns) == oasis.MAPPING_COLS
    by = out.set_index("node_key")
    assert by.loc["VINCENT", "pnode"] == "HAND_PICKED_2_N001" and by.loc["VINCENT", "confirmed"] == "yes"
    assert by.loc["VINCENT", "note"] == "confirmed by hand"
    assert by.loc["WINDHUB", "pnode"] == "WINDHUB_2_N001" and by.loc["WINDHUB", "confirmed"] == "no"
    assert "score=1.00" in by.loc["WINDHUB", "note"] and "WINDHUB_7_N005" in by.loc["WINDHUB", "note"]
    assert by.loc["RED BLUFF", "pnode"] == "REDBLUF_2_N101" and by.loc["RED BLUFF", "confirmed"] == "no"
    assert "DELANEY COLORADO RIVER" not in by.index            # no candidate: nothing invented
    assert "GATES" not in by.index                              # outside top_n
    assert by.loc["OLD NODE", "pnode"] == "OLDNODE_2_N001"      # untouched unconfirmed row survives
    assert (out.confirmed == "yes").sum() == 1
    assert not out.pnode.isin([""]).any()


def test_suggest_pnode_column_detection_falls_back():
    pn = pd.DataFrame({"SOMETHING": ["WINDHUB_2_N001"]})
    assert oasis.pnode_name_column(pn) == "SOMETHING"
    assert oasis.pnode_name_column(pd.DataFrame({"x": [1], "APNODE_ID": ["A"], "PNODE_ID": ["B"]})) == "PNODE_ID"


# ------------------------------------------------------------------- mapping protections

def test_confirmed_requires_yes_and_a_pnode():
    m = pd.DataFrame([
        dict(node_key="A", pnode="A_2_N001", confirmed="yes", note=""),
        dict(node_key="B", pnode="", confirmed="yes", note="yes but empty"),
        dict(node_key="C", pnode="C_2_N001", confirmed="no", note=""),
        dict(node_key="D", pnode="D_2_N001", confirmed="", note=""),
    ])
    assert oasis.confirmed(oasis.load_mapping_frame(m)).node_key.tolist() == ["A"]


def test_load_mapping_normalises_and_creates(tmp_path):
    p = tmp_path / "poi_pnodes.csv"
    assert oasis.load_mapping(p).empty and list(oasis.load_mapping(p).columns) == oasis.MAPPING_COLS
    p.write_text("node_key,pnode,confirmed,note\nA, A_2_N001 , YES ,ok\nB,,no,\n")
    m = oasis.load_mapping(p)
    assert m.confirmed.tolist() == ["yes", "no"] and m.pnode.tolist() == ["A_2_N001", ""]
    created = oasis.ensure_mapping(tmp_path / "new.csv")
    assert (created.confirmed == "no").all() and (created.pnode == "").all()
    assert (created.note == "fill from data/pnodes.csv").all() and len(created) == 3


def test_repo_mapping_file_has_only_placeholders():
    m = oasis.load_mapping(Path(__file__).resolve().parents[1] / "data" / "poi_pnodes.csv")
    assert list(m.columns) == oasis.MAPPING_COLS
    assert oasis.confirmed(m).empty or (oasis.confirmed(m).pnode != "").all()
    assert (m.loc[m.pnode == "", "confirmed"] == "no").all()


def test_fetch_never_queries_unconfirmed_nodes(tmp_path):
    mapping = pd.DataFrame([
        dict(node_key="WINDHUB", pnode="WINDHUB_2_N001", confirmed="yes", note=""),
        dict(node_key="RED BLUFF", pnode="REDBLUF_2_N101", confirmed="no", note="suggest score=0.9"),
        dict(node_key="VINCENT", pnode="", confirmed="yes", note="yes but no pnode"),
        dict(node_key="GATES", pnode="GATES_2_N001", confirmed="", note=""),
    ])
    calls = []

    def fake(pnode, start, end):
        calls.append((pnode, start, end))
        if pnode != "WINDHUB_2_N001":
            raise AssertionError(f"OASIS queried for an unconfirmed node: {pnode}")
        return prc_lmp_csv({f"{start:%Y-%m}-05": DAY1, f"{start:%Y-%m}-06": DAY2}, node=pnode)

    windows = oasis.month_windows(2, "2026-02")
    daily = oasis.fetch_daily(mapping, windows, downloader=fake, cache_dir=tmp_path, delay=0, log=lambda *a: None)
    assert [c[0] for c in calls] == ["WINDHUB_2_N001", "WINDHUB_2_N001"]
    assert daily.node_key.unique().tolist() == ["WINDHUB"] and len(daily) == 4
    assert daily.tb4.iloc[0] == pytest.approx(100 - 14.25) and daily.tb4.iloc[1] == 0


def test_fetch_uses_cache_and_skips_downloaded_months(tmp_path):
    mapping = pd.DataFrame([dict(node_key="WINDHUB", pnode="WINDHUB_2_N001", confirmed="yes", note="")])
    windows = oasis.month_windows(3, "2026-03")
    cached = tmp_path / "WINDHUB_2_N001" / "2026-01.csv"
    cached.parent.mkdir(parents=True)
    cached.write_text(prc_lmp_csv({"2026-01-10": DAY1}))
    calls = []

    def fake(pnode, start, end):
        calls.append((start, end))
        return prc_lmp_csv({f"{start:%Y-%m}-15": DAY2}, node=pnode)

    daily = oasis.fetch_daily(mapping, windows, downloader=fake, cache_dir=tmp_path, delay=0, log=lambda *a: None)
    assert len(calls) == 2                                     # 2026-02 and 2026-03 only
    assert calls[0][0] == pd.Timestamp("2026-02-01 08:00") and calls[0][1] == pd.Timestamp("2026-03-01 08:00")
    assert (tmp_path / "WINDHUB_2_N001" / "2026-02.csv").exists() and (tmp_path / "WINDHUB_2_N001" / "2026-03.csv").exists()
    assert daily.date.tolist() == [pd.Timestamp("2026-01-10"), pd.Timestamp("2026-02-15"), pd.Timestamp("2026-03-15")]
    # second run: everything cached, no calls
    calls.clear()
    oasis.fetch_daily(mapping, windows, downloader=fake, cache_dir=tmp_path, delay=0, log=lambda *a: None)
    assert calls == []


def test_fetch_errors_propagate_and_keep_cache(tmp_path):
    mapping = pd.DataFrame([dict(node_key="WINDHUB", pnode="WINDHUB_2_N001", confirmed="yes", note="")])
    windows = oasis.month_windows(2, "2026-02")

    def fake(pnode, start, end):
        if start.month == 2:
            raise RuntimeError("OASIS returned no CSV")
        return prc_lmp_csv({"2026-01-05": DAY1}, node=pnode)

    with pytest.raises(RuntimeError):
        oasis.fetch_daily(mapping, windows, downloader=fake, cache_dir=tmp_path, delay=0, log=lambda *a: None)
    assert (tmp_path / "WINDHUB_2_N001" / "2026-01.csv").exists()
    assert not (tmp_path / "WINDHUB_2_N001" / "2026-02.csv").exists()


def test_fetch_daily_empty_when_nothing_confirmed(tmp_path):
    def boom(*a):
        raise AssertionError("must not be called")
    d = oasis.fetch_daily(pd.DataFrame(columns=oasis.MAPPING_COLS), oasis.month_windows(1, "2026-01"),
                          downloader=boom, cache_dir=tmp_path, delay=0)
    assert d.empty and "tb4" in d.columns


# ------------------------------------------------------------------- OASIS URL / zip plumbing

def test_oasis_datetime_and_urls():
    assert oasis.oasis_datetime(pd.Timestamp("2026-01-01 08:00")) == "20260101T08:00-0000"
    u = oasis.prc_lmp_url("WINDHUB_2_N001", pd.Timestamp("2026-01-01 08:00"), pd.Timestamp("2026-02-01 08:00"))
    assert u.startswith("https://oasis.caiso.com/oasisapi/SingleZip?")
    for part in ("queryname=PRC_LMP", "startdatetime=20260101T08%3A00-0000", "enddatetime=20260201T08%3A00-0000",
                 "version=1", "market_run_id=DAM", "node=WINDHUB_2_N001", "resultformat=6"):
        assert part in u, part
    a = oasis.atl_pnode_url(pd.Timestamp("2026-01-01 08:00"), pd.Timestamp("2026-01-02 08:00"))
    for part in ("queryname=ATL_PNODE", "version=1", "Pnode_type=ALL", "resultformat=6"):
        assert part in a, part


def test_month_windows():
    w = oasis.month_windows(3, "2026-08")
    assert [m for m, _, _ in w] == ["2026-06", "2026-07", "2026-08"]
    assert w[0][1] == pd.Timestamp("2026-06-01 08:00") and w[0][2] == pd.Timestamp("2026-07-01 08:00")
    assert all((e - s).days <= 31 for _, s, e in w)
    assert [m for m, _, _ in oasis.month_windows(2, "2026-01")] == ["2025-12", "2026-01"]
    last = pd.Period(pd.Timestamp.today(), freq="M") - 1
    assert oasis.month_windows(1)[0][0] == str(last)


def zip_bytes(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in members.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_unzip_csv_and_error_report(csv_two_days):
    assert oasis.unzip_csv(zip_bytes({"20260105_20260201_PRC_LMP_DAM_v1.csv": csv_two_days})) == csv_two_days
    with pytest.raises(RuntimeError, match="INVALID_REQUEST"):
        oasis.unzip_csv(zip_bytes({"INVALID_REQUEST.xml": "<m:ERR_CODE>1015</m:ERR_CODE> INVALID_REQUEST"}))


def test_fetch_prc_lmp_csv_uses_mocked_download(monkeypatch, csv_two_days):
    seen = {}

    def fake_download(url, timeout=120):
        seen["url"] = url
        return zip_bytes({"x.csv": csv_two_days})

    monkeypatch.setattr(oasis, "download", fake_download)
    text = oasis.fetch_prc_lmp_csv("WINDHUB_2_N001", pd.Timestamp("2026-01-01 08:00"), pd.Timestamp("2026-02-01 08:00"))
    assert text == csv_two_days and "node=WINDHUB_2_N001" in seen["url"]
    monkeypatch.setattr(oasis, "download", lambda url, timeout=120: zip_bytes({"p.csv": "PNODE_ID,PNODE_TYPE\nA_2_N001,N\n"}))
    assert oasis.fetch_pnodes_csv().startswith("PNODE_ID")


# ------------------------------------------------------------------- outputs + nodes.join_lmp

def test_write_outputs_and_join_lmp(tmp_path, monkeypatch, capsys):
    m, s = oasis.write_outputs(daily_frame(), out_dir=tmp_path)
    assert (tmp_path / "lmp_tb4.csv").exists() and (tmp_path / "lmp_tb4_summary.csv").exists()
    assert {"source_file", "pipeline_run"} <= set(m.columns) and (s.source_file == oasis.SOURCE).all()
    monkeypatch.setattr(nodes, "OUT", tmp_path)
    n = nodes.join_lmp(pd.DataFrame({"node_key": ["WINDHUB", "VINCENT", "GATES"]}))
    assert list(n.columns) == ["node_key", *nodes.LMP_COLS]
    by = n.set_index("node_key")
    assert by.loc["WINDHUB", "lmp_months"] == 2 and by.loc["WINDHUB", "lmp_tb4_12mo_p90"] == 80.0
    assert by.loc["VINCENT", "lmp_tb4_12mo_mean"] == 50.0
    assert by.loc["GATES", "lmp_months"] == 0 and np.isnan(by.loc["GATES", "lmp_tb4_12mo_mean"])
    assert "2 nodes with day-ahead TB4" in capsys.readouterr().out


def test_join_lmp_without_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(nodes, "OUT", tmp_path)
    n = nodes.join_lmp(pd.DataFrame({"node_key": ["A", "B"]}))
    assert list(n.columns) == ["node_key", *nodes.LMP_COLS]
    assert (n.lmp_months == 0).all() and n.lmp_tb4_12mo_mean.isna().all() and n.lmp_tb4_12mo_p90.isna().all()


# ------------------------------------------------------------------- CLI wiring

def test_cli_registers_oasis_but_not_in_weekly():
    assert "oasis" in cli.COMMANDS
    assert "oasis" in cli.__doc__
    assert "oasis" not in inspect.getsource(cli.weekly)


def test_cli_oasis_requires_subcommand(monkeypatch, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["oasis"])
    assert e.value.code == 2


def test_cli_fetch_exits_without_confirmed_rows(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(oasis, "MAPPING", tmp_path / "poi_pnodes.csv")
    with pytest.raises(SystemExit) as e:
        cli.main(["oasis", "fetch", "--months", "1"])
    assert "no confirmed rows" in str(e.value)
    assert (tmp_path / "poi_pnodes.csv").exists()          # placeholder mapping was created for the user


def test_cli_fetch_end_to_end_with_mocked_downloader(monkeypatch, tmp_path, capsys):
    mp = tmp_path / "poi_pnodes.csv"
    mp.write_text("node_key,pnode,confirmed,note\nWINDHUB,WINDHUB_2_N001,yes,checked\nRED BLUFF,REDBLUF_2_N101,no,\n")
    monkeypatch.setattr(oasis, "MAPPING", mp)
    monkeypatch.setattr(oasis, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(oasis, "OUT", tmp_path / "out")

    def fake(pnode, start, end):
        assert pnode == "WINDHUB_2_N001"
        return prc_lmp_csv({f"{start:%Y-%m}-05": DAY1}, node=pnode)

    monkeypatch.setattr(oasis, "fetch_prc_lmp_csv", fake)
    cli.main(["oasis", "fetch", "--months", "2", "--end", "2026-02", "--delay", "0"])
    s = pd.read_csv(tmp_path / "out" / "lmp_tb4_summary.csv")
    assert s.node_key.tolist() == ["WINDHUB"] and s.months.iloc[0] == 2
    assert s.tb4_12mo_mean.iloc[0] == pytest.approx(85.75)
    assert (tmp_path / "cache" / "WINDHUB_2_N001" / "2026-01.csv").exists()
    assert "wrote" in capsys.readouterr().out


def test_cli_suggest_end_to_end(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(oasis, "MAPPING", tmp_path / "poi_pnodes.csv")
    monkeypatch.setattr(oasis, "PNODES", tmp_path / "pnodes.csv")
    monkeypatch.setattr(oasis, "OUT", tmp_path)
    pnodes_frame(PNODES).to_csv(tmp_path / "pnodes.csv", index=False)
    pd.DataFrame({"node_key": ["WINDHUB", "VINCENT"], "pipeline_mw": [4600, 3520]}).to_csv(tmp_path / "nodes.csv", index=False)
    cli.main(["oasis", "suggest", "--top", "1"])
    m = oasis.load_mapping(tmp_path / "poi_pnodes.csv")
    assert (m.confirmed == "no").all()
    assert m.set_index("node_key").loc["WINDHUB", "pnode"] == "WINDHUB_2_N001"
    assert "confirmed=no" in capsys.readouterr().out


def test_fetch_daily_default_downloader_is_the_network_client(monkeypatch, tmp_path):
    assert inspect.signature(oasis.fetch_daily).parameters["delay"].default == oasis.POLITE_DELAY == 5.0
    mapping = pd.DataFrame([dict(node_key="WINDHUB", pnode="WINDHUB_2_N001", confirmed="yes", note="")])
    hit = []
    monkeypatch.setattr(oasis, "fetch_prc_lmp_csv", lambda p, s, e: hit.append(p) or prc_lmp_csv({"2026-01-05": DAY1}, node=p))
    monkeypatch.setattr(oasis, "CACHE", tmp_path)
    oasis.fetch_daily(mapping, oasis.month_windows(1, "2026-01"), delay=0, log=lambda *a: None)
    assert hit == ["WINDHUB_2_N001"] and (tmp_path / "WINDHUB_2_N001" / "2026-01.csv").exists()
