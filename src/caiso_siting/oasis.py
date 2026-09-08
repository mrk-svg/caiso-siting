"""
CAISO OASIS day-ahead LMP for a hand-confirmed set of nodes — the TB4 spread a storage developer
uses as the first revenue screen.

    caiso-siting oasis pnodes                 download CAISO's pricing-node list      -> data/pnodes.csv
    caiso-siting oasis suggest [--top 40]     fuzzy-match top nodes to PNode names    -> data/poi_pnodes.csv (confirmed=no)
    caiso-siting oasis fetch [--months 12]    day-ahead LMP for confirmed PNodes      -> outputs/lmp_tb4.csv, lmp_tb4_summary.csv

All three need the network: run them from your terminal, not in CI. OASIS rate-limits — the client
waits POLITE_DELAY (5 s) between calls and never retries in a loop.

The mapping file data/poi_pnodes.csv (node_key, pnode, confirmed, note) is hand-maintained. Nothing is
queried for a row unless confirmed == 'yes' with a non-empty pnode; `suggest` writes candidates with
confirmed='no' and never touches a confirmed row. PNode ids are never guessed by code — they come from
data/pnodes.csv (ATL_PNODE) and a human confirms each one against the POI it belongs to.

OASIS SingleZip API (https://oasis.caiso.com/oasisapi/SingleZip): one GET per query, the response is a zip
holding one CSV (resultformat=6). Datetimes are YYYYMMDDTHH:MM-0000 (UTC). A single PRC_LMP request may
span at most ~31 days, so `fetch` goes month by month and caches each raw CSV under
data/oasis_cache/<pnode>/<YYYY-MM>.csv; cached months are never re-downloaded.

Metric: TB4 spread, per day = mean of the 4 highest hourly DAM LMPs minus mean of the 4 lowest ($/MWh).
It is the arbitrage a 4-hour battery with perfect foresight would capture on energy alone — a
first-pass storage revenue screen, not a revenue forecast (no RA, no ancillary services, no real-time,
no degradation, no losses). Days with fewer than MIN_HOURS hourly prices are dropped.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
import zipfile
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from .common import norm_poi
from .config import DATA, OUT, add_provenance

OASIS_BASE = "https://oasis.caiso.com/oasisapi/SingleZip"
POLITE_DELAY = 5.0          # seconds between OASIS calls; OASIS throttles and blocks bursts
MIN_HOURS = 8               # a day needs at least 8 prices for top-4 minus bottom-4 to mean anything
MATCH_MIN = 0.85            # same fuzzy rule as nodes.Geocoder
MAPPING = DATA / "poi_pnodes.csv"
PNODES = DATA / "pnodes.csv"
CACHE = DATA / "oasis_cache"
MAPPING_COLS = ["node_key", "pnode", "confirmed", "note"]
SOURCE = "CAISO OASIS PRC_LMP DAM"

Downloader = Callable[[str, pd.Timestamp, pd.Timestamp], str]


# ------------------------------------------------------------------ OASIS client (network)

def oasis_datetime(ts: pd.Timestamp) -> str:
    """OASIS wants YYYYMMDDTHH:MM-0000 (UTC)."""
    return f"{pd.Timestamp(ts):%Y%m%dT%H:%M}-0000"


def oasis_url(**params) -> str:
    from urllib.parse import urlencode
    return f"{OASIS_BASE}?{urlencode(params)}"


def prc_lmp_url(pnode: str, start: pd.Timestamp, end: pd.Timestamp) -> str:
    return oasis_url(queryname="PRC_LMP", startdatetime=oasis_datetime(start), enddatetime=oasis_datetime(end),
                     version=1, market_run_id="DAM", node=pnode, resultformat=6)


def atl_pnode_url(start: pd.Timestamp, end: pd.Timestamp) -> str:
    return oasis_url(queryname="ATL_PNODE", startdatetime=oasis_datetime(start), enddatetime=oasis_datetime(end),
                     version=1, Pnode_type="ALL", resultformat=6)


def unzip_csv(content: bytes) -> str:
    """OASIS answers every SingleZip call with a zip. A CSV member is the data; an XML member is an error
    report (INVALID_REQUEST, no data for the window...) — surface it instead of parsing it."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        names = z.namelist()
        csvs = [n for n in names if n.lower().endswith(".csv")]
        if not csvs:
            detail = ""
            for n in names:
                if n.lower().endswith(".xml"):
                    detail = z.read(n).decode("utf-8", "replace")[:300]
            raise RuntimeError(f"OASIS returned no CSV (members: {names}) {detail}".strip())
        return z.read(csvs[0]).decode("utf-8", "replace")


def download(url: str, timeout: int = 120) -> bytes:
    import requests
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (caiso-siting oasis)"})
    r.raise_for_status()
    return r.content


def fetch_prc_lmp_csv(pnode: str, start: pd.Timestamp, end: pd.Timestamp) -> str:
    return unzip_csv(download(prc_lmp_url(pnode, start, end)))


def fetch_pnodes_csv(start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> str:
    if end is None:
        end = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() + pd.Timedelta(hours=8)
    end = pd.Timestamp(end)
    start = pd.Timestamp(start) if start is not None else end - pd.Timedelta(days=1)
    return unzip_csv(download(atl_pnode_url(start, end)))


def month_windows(months: int, end_month: str | None = None) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    """(YYYY-MM, start, end) for the `months` complete months ending at `end_month` (default: last month).
    Windows run 08:00 UTC to 08:00 UTC (midnight Pacific standard time) — during daylight time the first
    local hour of the month lands in the previous window; rows are keyed by OPR_DT so days still aggregate
    correctly and duplicate hours are dropped on concat."""
    if end_month:
        last = pd.Period(end_month, freq="M")
    else:
        last = pd.Period(pd.Timestamp.today(), freq="M") - 1
    out = []
    for i in range(months - 1, -1, -1):
        p = last - i
        start = p.to_timestamp(how="start") + pd.Timedelta(hours=8)
        end = (p + 1).to_timestamp(how="start") + pd.Timedelta(hours=8)
        out.append((str(p), start, end))
    return out


# ------------------------------------------------------------------ pure parsing / metrics

def parse_prc_lmp(csv_text: str) -> pd.DataFrame:
    """OASIS PRC_LMP CSV -> hourly frame (ts tz-naive local Pacific, lmp $/MWh, node). Keeps LMP_TYPE == 'LMP'
    (the total; MCE/MCC/MCL are its components). The price sits in OASIS's `MW` column. ts is OPR_DT +
    (OPR_HR - 1) hours so a day is a CAISO operating day; hour 25 (fall-back) stays on its day."""
    df = pd.read_csv(io.StringIO(csv_text), dtype=str)
    df.columns = [str(c).strip().upper() for c in df.columns]
    if "LMP_TYPE" in df.columns:
        df = df[df["LMP_TYPE"].str.strip().str.upper() == "LMP"]
    if "MARKET_RUN_ID" in df.columns:
        df = df[df["MARKET_RUN_ID"].str.strip().str.upper() == "DAM"]
    price_col = "MW" if "MW" in df.columns else next((c for c in df.columns if c in ("VALUE", "PRC", "LMP")), None)
    if price_col is None:
        raise ValueError(f"PRC_LMP CSV has no price column; columns: {list(df.columns)}")
    if {"OPR_DT", "OPR_HR"} <= set(df.columns):
        ts = pd.to_datetime(df["OPR_DT"], errors="coerce") + pd.to_timedelta(
            pd.to_numeric(df["OPR_HR"], errors="coerce") - 1, unit="h")
    else:
        ts = (pd.to_datetime(df["INTERVALSTARTTIME_GMT"], errors="coerce", utc=True)
              .dt.tz_convert("America/Los_Angeles").dt.tz_localize(None))
    out = pd.DataFrame({"ts": ts, "lmp": pd.to_numeric(df[price_col], errors="coerce"),
                        "node": df["NODE"].str.strip() if "NODE" in df.columns else ""})
    out = out.dropna(subset=["ts", "lmp"]).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    return out


def tb4_daily(df_hourly: pd.DataFrame, min_hours: int = MIN_HOURS) -> pd.DataFrame:
    """Per operating day: hours, lmp_mean, top4, bottom4, tb4 = top4 - bottom4 ($/MWh).
    Input columns: ts (tz-naive), lmp. Days with fewer than `min_hours` prices are dropped."""
    d = df_hourly[["ts", "lmp"]].dropna().copy()
    if d.empty:
        return pd.DataFrame(columns=["date", "hours", "lmp_mean", "top4", "bottom4", "tb4"])
    d["date"] = pd.to_datetime(d["ts"]).dt.normalize()
    g = d.groupby("date")["lmp"]
    out = g.agg(hours="size", lmp_mean="mean",
                top4=lambda s: s.nlargest(4).mean(),
                bottom4=lambda s: s.nsmallest(4).mean())
    out["tb4"] = out["top4"] - out["bottom4"]
    out = out[out["hours"] >= min_hours].reset_index()
    for c in ("lmp_mean", "top4", "bottom4", "tb4"):
        out[c] = out[c].round(2)
    return out


def _with_month(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["month"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d


def monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """outputs/lmp_tb4.csv rows: node_key, pnode, month, days, tb4_mean, tb4_p90, lmp_mean."""
    cols = ["node_key", "pnode", "month", "days", "tb4_mean", "tb4_p90", "lmp_mean"]
    if daily.empty:
        return pd.DataFrame(columns=cols)
    d = _with_month(daily)
    m = d.groupby(["node_key", "pnode", "month"]).agg(
        days=("tb4", "size"), tb4_mean=("tb4", "mean"), tb4_p90=("tb4", lambda s: s.quantile(0.9)),
        lmp_mean=("lmp_mean", "mean")).round(2).reset_index()
    return m[cols]


def summarise(daily: pd.DataFrame) -> pd.DataFrame:
    """outputs/lmp_tb4_summary.csv rows: one per node — months, tb4 mean / p90 and mean LMP over every
    day fetched (the 12-month window by default), first and last month."""
    cols = ["node_key", "pnode", "months", "tb4_12mo_mean", "tb4_12mo_p90", "lmp_12mo_mean", "first_month", "last_month"]
    if daily.empty:
        return pd.DataFrame(columns=cols)
    d = _with_month(daily)
    s = d.groupby(["node_key", "pnode"]).agg(
        months=("month", "nunique"), tb4_12mo_mean=("tb4", "mean"), tb4_12mo_p90=("tb4", lambda s: s.quantile(0.9)),
        lmp_12mo_mean=("lmp_mean", "mean"), first_month=("month", "min"), last_month=("month", "max")).reset_index()
    for c in ("tb4_12mo_mean", "tb4_12mo_p90", "lmp_12mo_mean"):
        s[c] = s[c].round(2)
    return s[cols].sort_values("tb4_12mo_mean", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------ mapping file

def load_mapping(path: Path | None = None) -> pd.DataFrame:
    path = Path(path) if path is not None else MAPPING
    if not path.exists():
        return pd.DataFrame(columns=MAPPING_COLS)
    m = pd.read_csv(path, dtype=str, comment="#").fillna("")
    for c in MAPPING_COLS:
        if c not in m.columns:
            m[c] = ""
    m["node_key"] = m["node_key"].str.strip()
    m["pnode"] = m["pnode"].str.strip()
    m["confirmed"] = m["confirmed"].str.strip().str.lower()
    return m[MAPPING_COLS]


def save_mapping(m: pd.DataFrame, path: Path | None = None) -> None:
    path = Path(path) if path is not None else MAPPING
    path.parent.mkdir(parents=True, exist_ok=True)
    m[MAPPING_COLS].to_csv(path, index=False)


def confirmed(m: pd.DataFrame) -> pd.DataFrame:
    """The only rows that are ever queried: confirmed == 'yes' with a PNode id present."""
    return m[(m["confirmed"] == "yes") & (m["pnode"] != "")].drop_duplicates("node_key")


def pnode_name_column(pnodes: pd.DataFrame) -> str:
    cols = [str(c) for c in pnodes.columns]
    for want in ("PNODE_ID", "PNODE_NAME", "PNODE", "NODE_ID", "NODE"):
        for c in cols:
            if c.strip().upper() == want:
                return c
    for c in cols:
        if "PNODE" in c.upper():
            return c
    return cols[0]


def match_pnode(node_key: str, names: list[str]) -> tuple[str | None, float, list[str]]:
    """Best PNode for a node_key by difflib ratio on norm_poi(name) and on the station stem before the
    first '_' (OASIS ids look like STEM_2_N001). Same rule as nodes.Geocoder: ratio >= MATCH_MIN and the
    same first token — OASIS stems are abbreviated single tokens (REDBLUF, WHIRLWD), so a one-token stem
    passes the first-token test when it starts with the first three letters of the key's first token
    (MOSS LANDING still never lands on ROSSLND or CROWSLD). Returns (best, score, alternatives >= MATCH_MIN)."""
    k = norm_poi(node_key)
    if not k:
        return None, 0.0, []
    first = k.split()[0]
    best, score = None, 0.0
    scored: list[tuple[float, str]] = []
    for n in names:
        stem = norm_poi(str(n).split("_")[0])
        full = norm_poi(n)
        if not stem:
            continue
        toks = stem.split()
        same_first = toks[0] == first or (len(toks) == 1 and toks[0][:3] == first[:3])
        if not same_first:
            continue
        s = max(SequenceMatcher(None, k, stem).ratio(), SequenceMatcher(None, k, full).ratio())
        scored.append((s, str(n)))
        if s > score:
            best, score = str(n), s
    if best is None or score < MATCH_MIN:
        return None, score, []
    alts = sorted({n for s, n in scored if s >= MATCH_MIN and n != best})
    return best, round(score, 2), alts[:5]


def suggest(nodes: pd.DataFrame, pnodes: pd.DataFrame, mapping: pd.DataFrame, top_n: int = 40) -> pd.DataFrame:
    """For the top `top_n` nodes by pipeline_mw, write the best PNode candidate into the mapping with
    confirmed='no' and the score in `note`. Rows already confirmed='yes' are never overwritten; unconfirmed
    rows for the same node_key are replaced by the fresh suggestion; nodes without a match are left as they are."""
    m = load_mapping_frame(mapping)
    names = pnodes[pnode_name_column(pnodes)].dropna().astype(str).str.strip().unique().tolist()
    top = nodes.sort_values("pipeline_mw", ascending=False).drop_duplicates("node_key").head(top_n)
    keep_yes = m[m["confirmed"] == "yes"]
    locked = set(keep_yes["node_key"])
    rows = []
    for nk in top["node_key"]:
        if nk in locked:
            continue
        best, score, alts = match_pnode(nk, names)
        if best is None:
            continue
        note = f"suggest score={score:.2f}"
        if alts:
            note += " alt: " + "; ".join(alts)
        note += " — verify against data/pnodes.csv before setting confirmed=yes"
        rows.append(dict(node_key=nk, pnode=best, confirmed="no", note=note))
    suggested = pd.DataFrame(rows, columns=MAPPING_COLS)
    rest = m[(m["confirmed"] != "yes") & ~m["node_key"].isin(set(suggested["node_key"]))]
    out = pd.concat([keep_yes, suggested, rest], ignore_index=True)[MAPPING_COLS]
    return out.drop_duplicates(["node_key", "pnode"]).reset_index(drop=True)


def load_mapping_frame(mapping: pd.DataFrame | Path | str) -> pd.DataFrame:
    if isinstance(mapping, pd.DataFrame):
        m = mapping.copy().fillna("")
        for c in MAPPING_COLS:
            if c not in m.columns:
                m[c] = ""
        m["confirmed"] = m["confirmed"].astype(str).str.strip().str.lower()
        m["pnode"] = m["pnode"].astype(str).str.strip()
        return m[MAPPING_COLS]
    return load_mapping(Path(mapping))


# ------------------------------------------------------------------ fetch orchestration

def fetch_daily(mapping: pd.DataFrame, windows: list[tuple[str, pd.Timestamp, pd.Timestamp]],
                downloader: Downloader | None = None, cache_dir: Path | None = None,
                delay: float = POLITE_DELAY, log=print) -> pd.DataFrame:
    """Daily TB4 rows (node_key, pnode, date, hours, lmp_mean, top4, bottom4, tb4) for every confirmed node.
    Only rows from `confirmed(mapping)` reach the downloader (default: the OASIS client `fetch_prc_lmp_csv`).
    Raw CSVs are cached per pnode per month under `cache_dir` (default CACHE); a cached month is read back and
    never re-downloaded. Errors propagate — re-running resumes from the cache."""
    downloader = downloader or fetch_prc_lmp_csv
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE
    frames = []
    calls = 0
    for r in confirmed(mapping).itertuples(index=False):
        hourly = []
        for month, start, end in windows:
            path = cache_dir / r.pnode / f"{month}.csv"
            if path.exists():
                text = path.read_text()
            else:
                if calls and delay:
                    time.sleep(delay)
                text = downloader(r.pnode, start, end)
                calls += 1
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
                log(f"oasis: {r.pnode} {month} downloaded ({len(text):,} bytes)")
            hourly.append(parse_prc_lmp(text))
        h = pd.concat(hourly, ignore_index=True) if hourly else pd.DataFrame(columns=["ts", "lmp"])
        h = h.drop_duplicates("ts").sort_values("ts")
        d = tb4_daily(h)
        d.insert(0, "pnode", r.pnode)
        d.insert(0, "node_key", r.node_key)
        frames.append(d)
        tb4 = f"TB4 mean {d.tb4.mean():.1f} $/MWh" if len(d) else "no data"
        log(f"oasis: {r.node_key} -> {r.pnode}: {len(h)} hours, {len(d)} days, {tb4}")
    cols = ["node_key", "pnode", "date", "hours", "lmp_mean", "top4", "bottom4", "tb4"]
    return pd.concat(frames, ignore_index=True)[cols] if frames else pd.DataFrame(columns=cols)


def write_outputs(daily: pd.DataFrame, out_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    out_dir = Path(out_dir) if out_dir is not None else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    m = add_provenance(monthly(daily), SOURCE)
    s = add_provenance(summarise(daily), SOURCE)
    m.to_csv(out_dir / "lmp_tb4.csv", index=False)
    s.to_csv(out_dir / "lmp_tb4_summary.csv", index=False)
    return m, s


# ------------------------------------------------------------------ CLI

EXAMPLE_ROWS = [  # placeholders only: PNode ids are never guessed, fill them from data/pnodes.csv
    dict(node_key="WINDHUB", pnode="", confirmed="no", note="fill from data/pnodes.csv"),
    dict(node_key="RED BLUFF", pnode="", confirmed="no", note="fill from data/pnodes.csv"),
    dict(node_key="VINCENT", pnode="", confirmed="no", note="fill from data/pnodes.csv"),
]


def ensure_mapping(path: Path | None = None) -> pd.DataFrame:
    path = Path(path) if path is not None else MAPPING
    if not path.exists():
        save_mapping(pd.DataFrame(EXAMPLE_ROWS, columns=MAPPING_COLS), path)
        print(f"created {path} with placeholder rows (confirmed=no) — fill pnode from {PNODES}")
    return load_mapping(path)


def cmd_pnodes(args) -> None:
    text = fetch_pnodes_csv()
    PNODES.parent.mkdir(parents=True, exist_ok=True)
    PNODES.write_text(text)
    df = pd.read_csv(io.StringIO(text), dtype=str)
    print(f"wrote {PNODES}: {len(df)} pricing nodes, columns {list(df.columns)}")


def cmd_suggest(args) -> None:
    if not PNODES.exists():
        sys.exit(f"{PNODES} missing — run `caiso-siting oasis pnodes` first (needs internet)")
    nodes_path = OUT / "nodes.csv"
    if not nodes_path.exists():
        sys.exit(f"{nodes_path} missing — run `caiso-siting nodes` first")
    m = ensure_mapping()
    pn = pd.read_csv(PNODES, dtype=str)
    nodes = pd.read_csv(nodes_path, usecols=["node_key", "pipeline_mw"])
    out = suggest(nodes, pn, m, top_n=args.top)
    save_mapping(out)
    new = out[out["confirmed"] != "yes"]
    print(f"{MAPPING}: {len(out)} rows, {(out['confirmed'] == 'yes').sum()} confirmed (untouched), "
          f"{len(new)} suggestions with confirmed=no — verify each and set confirmed=yes by hand")
    if len(new):
        print(new[["node_key", "pnode", "note"]].to_string(index=False))


def cmd_fetch(args) -> None:
    m = ensure_mapping()
    c = confirmed(m)
    if c.empty:
        sys.exit(f"no confirmed rows in {MAPPING} (confirmed=yes with a pnode) — nothing to fetch")
    windows = month_windows(args.months, args.end)
    print(f"fetching DAM PRC_LMP for {len(c)} confirmed nodes × {len(windows)} months "
          f"({windows[0][0]}..{windows[-1][0]}); ~{POLITE_DELAY:.0f} s between OASIS calls, cache {CACHE}")
    daily = fetch_daily(m, windows, delay=args.delay)
    mo, s = write_outputs(daily)
    print(s.to_string(index=False) if len(s) else "no daily rows")
    print(f"wrote {OUT / 'lmp_tb4.csv'} ({len(mo)} node-months), {OUT / 'lmp_tb4_summary.csv'} ({len(s)} nodes); "
          f"nodes.csv picks them up on the next `caiso-siting nodes` run")


def main() -> None:
    ap = argparse.ArgumentParser(prog="caiso-siting oasis", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pnodes", help="download the ATL_PNODE list -> data/pnodes.csv (needs internet)")
    sg = sub.add_parser("suggest", help="fuzzy-match top nodes to PNode names -> data/poi_pnodes.csv (confirmed=no)")
    sg.add_argument("--top", type=int, default=40, help="top N nodes by pipeline_mw (default 40)")
    fe = sub.add_parser("fetch", help="DAM LMP month by month for confirmed nodes -> outputs/lmp_tb4*.csv (needs internet)")
    fe.add_argument("--months", type=int, default=12)
    fe.add_argument("--end", default=None, help="last month YYYY-MM (default: last complete month)")
    fe.add_argument("--delay", type=float, default=POLITE_DELAY, help="seconds between OASIS calls")
    args = ap.parse_args()
    try:
        {"pnodes": cmd_pnodes, "suggest": cmd_suggest, "fetch": cmd_fetch}[args.cmd](args)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
