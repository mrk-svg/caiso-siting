"""Static site for GitHub Pages: `caiso-siting site` -> site/

  index.html          headline numbers, top-40 nodes, official C16 POI statements
  map.html            outputs/nodes_map.html copied verbatim (self-contained Leaflet)
  nodes/<slug>.html   one page per node with pipeline, operating or active WDAT MW
  note.html           outputs/node_watch.md rendered
  survival.html       Kaplan–Meier withdrawal survival by cluster (outputs/survival_*.csv, inline SVG)
  diff.html           outputs/diff_latest.md rendered (or a placeholder until two snapshots exist)

No template engine: stdlib string.Template + f-strings. No external assets except the Leaflet CDN
already inside map.html. Every page repeats the same disclaimer because every number on it needs it.
"""
from __future__ import annotations

import html
import re
import shutil
import sys
import time
from pathlib import Path
from string import Template

import pandas as pd

from .config import OUT, RECENT_YEARS, SITE
from .nodes import APPROX_METHODS

DISCLAIMER = ('No figure on this site states a cause. CAISO files carry no withdrawal reason beyond '
              '"IC Request".')

WDAT_NOTE = "WDAT = distribution-level queue at the same substation, PG&E file today; not CAISO deliverability"
WDAT_COLS = ["queue_position", "status_raw", "process", "gen_type", "net_mw", "request_received", "current_cod",
             "ia_status"]
WDAT_CAP = 50

# One-line definitions, copied from the docstring at the top of nodes.py (plus the three storage /
# FCDS columns that docstring omits, defined from the code that computes them).
METRIC_DEFS = [
    ("legacy_active_mw", "active MW in the public report (C14 and earlier)"),
    ("c15_active_mw", "active MW in the Cluster 15 report"),
    ("operating_mw", "completed MW in the public report"),
    ("pipeline_storage_mw", "storage MW inside legacy_active_mw + c15_active_mw"),
    ("operating_storage_mw", "storage MW inside operating_mw (completed, public report)"),
    ("wd_recent_mw", f"withdrawn in the last {RECENT_YEARS} years (both reports)"),
    ("wd_recent_storage_mw", "storage MW of those rows — each project's storage components capped at its "
                             "net-to-grid figure; a handful of filings report net-to-grid as 0 and keep the "
                             "component MW, so this can exceed the row above at 3 nodes."),
    ("wd_post_phase2_mw", "withdrew AFTER Phase II / Facilities Study results (public report only)"),
    ("wd_alltime_mw", "every withdrawn MW since 2006 (includes dead wind/solar-era projects)"),
    ("storage_churn", "wd_recent_storage_mw / (active + operating storage MW) — the one to quote"),
    ("churn_alltime", "wd_alltime_mw / (pipeline + operating MW) — historical color only"),
    ("c15_survival", "c15_active / (c15_active + c15_withdrawn)"),
    ("c15_fcds_req_mw", "C15 active MW that requested Full Capacity Deliverability Status (requested, not allocated)"),
    ("tpd25_projects", "projects at the node that sought TPD in CAISO's 2025 allocation cycle"),
    ("tpd25_req_mw", "MW at the node that sought TPD in CAISO's 2025 allocation cycle"),
    ("tpd25_alloc_mw", "MW allocated in that cycle (requested × allocation %)"),
    ("tpd25_denied_mw", "MW requested by rows that received 0 %"),
    ("tpd25_unalloc_mw", "requested minus allocated: MW refused outright PLUS the remainder left by partial "
                         "allocations — quote this for 'what the developer did not get'"),
    ("tpd25_unknown_mw", "MW requested by rows with no allocation percentage in the file; 0 today"),
    ("tpd24_fcdsa_projects", "projects at the node allocated Full Capacity in the 2024 cycle"),
    ("wdat_active_projects", f"active WDAT requests at the same substation ({WDAT_NOTE})"),
    ("wdat_active_mw", "MW of active WDAT (distribution-level) requests at the same substation (PG&E file today)"),
    ("wdat_active_storage_mw", "storage MW attributed from wdat_active_mw — an assumption: the PG&E file "
                               "publishes one MW figure per request, so storage-only requests count in full "
                               "and solar+storage requests count at half (160 of 1,011 active requests carry storage; "
                               "362 of their 479 MW is attributed as storage)."),
    ("wdat_inservice_mw", "WDAT MW already in service at that substation"),
    ("wdat_withdrawn_mw", "WDAT MW withdrawn at that substation (all-time in the file)"),
]

TOP_COLS = ["poi_base", "county", "utility", "legacy_active_mw", "c15_active_mw", "operating_mw",
            "wd_recent_mw", "storage_churn", "c15_survival", "tpd25_denied_mw", "wdat_active_mw", "c16_poi_status"]

CSS = """
:root{--fg:#1b1b1b;--muted:#5b5b5b;--bg:#fbfbf9;--line:#dcdcd6;--card:#fff;--accent:#1d4ed8;--warn:#9a3412;--warnbg:#fff4ec}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{border-bottom:1px solid var(--line);background:var(--card)}
header .in{max-width:1180px;margin:0 auto;padding:10px 16px;display:flex;flex-wrap:wrap;gap:6px 18px;
  align-items:baseline}
header .brand{font-weight:700;margin-right:auto}
header nav a{white-space:nowrap}
main{max-width:1180px;margin:0 auto;padding:16px}
h1{font-size:1.6rem;margin:.2em 0 .3em}
h2{font-size:1.2rem;margin:1.4em 0 .4em;border-bottom:1px solid var(--line);padding-bottom:.2em}
h3{font-size:1.05rem;margin:1.2em 0 .3em}
.sub{color:var(--muted);margin:0 0 .8em}
.disclaimer{background:var(--warnbg);border-left:4px solid var(--warn);padding:8px 12px;margin:12px 0;font-size:.92rem}
.warn{color:var(--warn);font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:14px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.tile .n{font-size:1.5rem;font-weight:700;line-height:1.15}.tile .l{color:var(--muted);font-size:.85rem}
.tbl{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:8px;margin:8px 0 16px}
table{border-collapse:collapse;width:100%;font-size:.9rem;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}
th{background:#f1f1ec;position:sticky;top:0}
td.num,th.num{text-align:right}
tr:last-child td{border-bottom:0}
td.wrap,th.wrap{white-space:normal;min-width:16em}
dl.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:8px 0}
dl.kv dt{font-weight:600}dl.kv dd{margin:0}
.md table{width:auto}
.chart{max-width:760px;margin:12px 0}.chart svg{width:100%;height:auto;display:block}
.md pre,.md code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em}
.md code{background:#eeeee8;padding:1px 4px;border-radius:3px}
footer{max-width:1180px;margin:24px auto 40px;padding:12px 16px;border-top:1px solid var(--line);color:var(--muted);
  font-size:.85rem}
footer p{margin:.3em 0}
@media (max-width:600px){body{font-size:14px}main{padding:10px}th,td{padding:5px 7px}}
"""

PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title · CAISO node intelligence</title>
<style>$css</style>
</head>
<body>
<header><div class="in">
<span class="brand"><a href="${root}index.html">CAISO node intelligence</a></span>
<nav><a href="${root}index.html">Home</a> · <a href="${root}map.html">Map</a> ·
<a href="${root}note.html">Node Watch</a> · <a href="${root}survival.html">Survival</a> ·
<a href="${root}diff.html">Weekly diff</a></nav>
</div></header>
<main>
$body
<p class="disclaimer">$disclaimer</p>
</main>
<footer>
<p>Sources: CAISO Public Queue Report and Cluster 15 Interconnection Requests report (CAISO report run date $run_date);
CAISO 2024 and 2025 Transmission Plan Deliverability allocation cycle results;
CAISO / PTO notices on Cluster 16 POI availability; substation positions &copy; OpenStreetMap contributors, ODbL;
PG&amp;E Wholesale Distribution Queue (WDAT); parcel and zoning layers from Kings County and Kern County GIS.</p>
<p>All MW are net-to-grid as filed. Cluster 15 deliverability is requested, not allocated.
Nothing here is load-side.</p>
<p>Pipeline commit <code>$commit</code> · pipeline run <code>$run</code> · site built <code>$built</code></p>
</footer>
</body>
</html>
""")


# ------------------------------------------------------------------ helpers

def esc(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return html.escape(str(v), quote=True)


def fmt(col: str, v) -> str:
    """MW columns as integers with thousands separators, ratios to 2 dp, NaN as n/a."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return "n/a" if col in ("storage_churn", "churn_alltime", "c15_survival", "geo_score") else ""
    if col.endswith("_mw") or col.endswith("_projects"):
        return f"{float(v):,.0f}"
    if col in ("storage_churn", "churn_alltime", "c15_survival", "geo_score"):
        return f"{float(v):.2f}"
    if col in ("lat", "lon"):
        return f"{float(v):.5f}"
    return esc(v)


def is_num(col: str) -> bool:
    return col.endswith(("_mw", "_projects")) or col in ("storage_churn", "churn_alltime", "c15_survival", "geo_score", "lat", "lon",
                                          "queue_position")


def date_only(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return ""
    s = str(v)
    return s[:10] if re.match(r"\d{4}-\d{2}-\d{2}", s) else esc(s)


def slugify(key: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(key).lower()).strip("-")
    return s or "node"


def unique_slugs(keys) -> dict[str, str]:
    out, seen = {}, {}
    for k in keys:
        s = slugify(k)
        n = seen.get(s, 0)
        seen[s] = n + 1
        out[k] = s if n == 0 else f"{s}-{n + 1}"
    return out


def table(df: pd.DataFrame, cols: list[str], links: dict[str, str] | None = None, link_col: str = "poi_base",
          key_col: str = "node_key", wrap: tuple[str, ...] = ()) -> str:
    """Plain HTML table. `links` maps key_col values to hrefs; rows without a link render as text."""
    head = "".join(f'<th class="{"num" if is_num(c) else ""}{" wrap" if c in wrap else ""}">{esc(c)}</th>'
                   for c in cols)
    rows = []
    for r in df.itertuples(index=False):
        d = r._asdict()
        cells = []
        for c in cols:
            v = d.get(c)
            txt = fmt(c, v)
            if links is not None and c == link_col and d.get(key_col) in links and txt:
                txt = f'<a href="{links[d[key_col]]}">{txt}</a>'
            cls = ("num" if is_num(c) else "") + (" wrap" if c in wrap else "")
            cells.append(f'<td class="{cls.strip()}">{txt}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    body = "".join(rows) if rows else f'<tr><td colspan="{len(cols)}"><i>none</i></td></tr>'
    return f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


# ------------------------------------------------------------------ tiny markdown -> html

_INLINE = [
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)"), r"<i>\1</i>"),
    (re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?!\w)"), r"<i>\1</i>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)"), r'<a href="\2">\1</a>'),
]


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    for rx, rep in _INLINE:
        s = rx.sub(rep, s)
    return s


def _md_table(lines: list[str]) -> str:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c or "--") for c in r)]
    if not rows:
        return ""
    aligns = []
    if len(lines) > 1:
        sep = [c.strip() for c in lines[1].strip().strip("|").split("|")]
        aligns = ["num" if c.endswith(":") and not c.startswith(":") else "" for c in sep]
    head, body = rows[0], rows[1:]

    def cell(tag, i, c):
        a = aligns[i] if i < len(aligns) else ""
        return f'<{tag} class="{a}">{_inline(c)}</{tag}>'
    h = "<tr>" + "".join(cell("th", i, c) for i, c in enumerate(head)) + "</tr>"
    b = "".join("<tr>" + "".join(cell("td", i, c) for i, c in enumerate(r)) + "</tr>" for r in body)
    return f'<div class="tbl"><table><thead>{h}</thead><tbody>{b}</tbody></table></div>'


def md_to_html(text: str) -> str:
    """Headings, pipe tables, bullet / numbered lists, paragraphs, inline bold/italic/code/links. Nothing else."""
    out: list[str] = []
    para: list[str] = []
    lst: list[str] = []
    lst_tag = ""
    tbl: list[str] = []

    def flush_para():
        if para:
            out.append("<p>" + _inline(" ".join(s.strip() for s in para)) + "</p>")
            para.clear()

    def flush_list():
        nonlocal lst_tag
        if lst:
            out.append(f"<{lst_tag}>" + "".join(f"<li>{_inline(i)}</li>" for i in lst) + f"</{lst_tag}>")
            lst.clear()
            lst_tag = ""

    def flush_tbl():
        if tbl:
            out.append(_md_table(tbl))
            tbl.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("|"):
            flush_para()
            flush_list()
            tbl.append(line)
            continue
        flush_tbl()
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_para()
            flush_list()
            lvl = min(len(m.group(1)), 4)
            out.append(f"<h{lvl}>{_inline(m.group(2).strip())}</h{lvl}>")
            continue
        m = re.match(r"^\s*([-*]|\d+[.)])\s+(.*)$", line)
        if m:
            flush_para()
            tag = "ol" if m.group(1)[0].isdigit() else "ul"
            if lst and lst_tag != tag:
                flush_list()
            lst_tag = tag
            lst.append(m.group(2))
            continue
        if not line.strip():
            flush_para()
            flush_list()
            continue
        if lst and raw.startswith("  "):          # continuation of a wrapped list item
            lst[-1] += " " + line.strip()
            continue
        flush_list()
        para.append(line)
    flush_para()
    flush_list()
    flush_tbl()
    return '<div class="md">' + "\n".join(out) + "</div>"


# ------------------------------------------------------------------ data

def load_projects(nodes: pd.DataFrame) -> pd.DataFrame:
    """Every project row from both reports, normalised to one column set for the node pages."""
    frames = []
    for name, cod_col in (("projects_all.csv", "current_cod"), ("cluster15_projects.csv", "proposed_cod")):
        p = OUT / name
        if not p.exists():
            print(f"warning: {p} missing; node pages will omit its projects", file=sys.stderr)
            continue
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
        for c in ("ia_status", "deliverability", "withdrawn_date", "cluster", "storage_mw", "net_mw", "queue_position",
                  "project_name", "sheet_status", "node_key", cod_col):
            if c not in df:
                df[c] = ""
        df["cod"] = df[cod_col].map(date_only)
        df["withdrawn_date"] = df["withdrawn_date"].map(date_only)
        df["report"] = "PUBLIC" if name.startswith("projects_all") else "C15"
        frames.append(df[["node_key", "project_name", "queue_position", "sheet_status", "cluster", "net_mw",
                          "storage_mw", "deliverability", "ia_status", "cod", "withdrawn_date", "report"]])
    if not frames:
        return pd.DataFrame(columns=["node_key", "project_name", "queue_position", "sheet_status", "cluster", "net_mw",
                                     "storage_mw", "deliverability", "ia_status", "cod", "withdrawn_date", "report"])
    df = pd.concat(frames, ignore_index=True)
    for c in ("net_mw", "storage_mw"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    order = {"ACTIVE": 0, "COMPLETED": 1, "WITHDRAWN": 2}
    df["_o"] = df.sheet_status.map(order).fillna(3)
    return df.sort_values(["_o", "net_mw"], ascending=[True, False]).drop(columns="_o")


def headline(projects: pd.DataFrame) -> list[tuple[str, str]]:
    pub, c15 = projects[projects.report == "PUBLIC"], projects[projects.report == "C15"]
    la = pub[pub.sheet_status == "ACTIVE"]
    ca = c15[c15.sheet_status == "ACTIVE"]
    cw = c15[c15.sheet_status == "WITHDRAWN"]
    return [
        (f"{len(la):,}", "legacy active projects (C14 and earlier)"),
        (f"{la.net_mw.sum():,.0f} MW", "legacy active MW"),
        (f"{len(ca):,}", "Cluster 15 active projects"),
        (f"{ca.net_mw.sum():,.0f} MW", "Cluster 15 active MW"),
        (f"{len(cw):,} / {cw.net_mw.sum():,.0f} MW", "Cluster 15 withdrawn since intake"),
    ]


# ------------------------------------------------------------------ pages

def render(title: str, body: str, root: str, prov: dict) -> str:
    return PAGE.substitute(title=esc(title), css=CSS, body=body, root=root, disclaimer=esc(DISCLAIMER), **prov)


def index_page(nodes: pd.DataFrame, projects: pd.DataFrame, slugs: dict[str, str], prov: dict) -> str:
    links = {k: f"nodes/{s}.html" for k, s in slugs.items()}
    tiles = "".join(f'<div class="tile"><div class="n">{esc(n)}</div><div class="l">{esc(lbl)}</div></div>'
                    for n, lbl in headline(projects))
    top = nodes.sort_values("pipeline_mw", ascending=False).head(40)
    avail = nodes[nodes.c16_poi_status.fillna("") != ""].sort_values(["c16_poi_status", "pipeline_mw"],
                                                                     ascending=[True, False])
    n_pages = len(slugs)
    tpd = nodes[nodes.get("tpd25_req_mw", pd.Series(0, index=nodes.index)) > 0] \
        .sort_values("tpd25_req_mw", ascending=False).head(15)
    wdat_top = nodes[nodes.get("wdat_active_mw", pd.Series(0, index=nodes.index)) > 0] \
        .sort_values("wdat_active_mw", ascending=False).head(10)
    body = f"""<h1>CAISO interconnection nodes</h1>
<p class="sub">Public Queue Report + Cluster 15 report, unified per point of interconnection, joined to official
Cluster 16 POI statements. CAISO report run date {esc(prov['run_date'])}. Every number traces to a CAISO row.</p>
<div class="tiles">{tiles}</div>
<p><a href="map.html">Map</a> (size = pipeline MW, fill = storage churn) ·
<a href="diff.html">Weekly diff</a> · <a href="note.html">Node Watch note</a> ·
<a href="survival.html">Survival by cluster</a> · {n_pages} node pages.</p>
<h2>Top 40 nodes by pipeline MW (legacy active + Cluster 15 active)</h2>
<p class="sub">storage_churn = storage MW withdrawn in the last {RECENT_YEARS} years ÷ (active + operating storage MW).
c15_survival = C15 active ÷ (C15 active + C15 withdrawn). Click a node for its projects and geocode provenance.</p>
{table(top, TOP_COLS, links)}
<h2>TPD allocation, 2025 cycle</h2>
<p class="sub">Top 15 nodes by MW that sought Transmission Plan Deliverability in CAISO's 2025 allocation cycle.</p>
{table(tpd, ['poi_base', 'county', 'utility', 'tpd25_req_mw', 'tpd25_alloc_mw', 'tpd25_unalloc_mw',
             'tpd25_denied_mw', 'tpd24_fcdsa_projects'], links)}
<p>"Denied" is MW refused outright (0 %); "unalloc" is requested minus allocated, so it also carries the remainder
left by partial allocations. These rows are joined through all three sheets of the public report, so a node's TPD
history can include requests whose project has since withdrawn. The CAISO file states no reason.</p>
<h2>Distribution-level (WDAT) activity at CAISO nodes</h2>
<p class="sub">Top 10 CAISO nodes by active MW in the wholesale distribution (WDAT) queue at the same substation.</p>
{table(wdat_top, ['poi_base', 'county', 'utility', 'wdat_active_projects', 'wdat_active_mw', 'wdat_inservice_mw'], links)}
<p>WDAT requests connect below CAISO's transmission grid; they carry no CAISO deliverability unless separately studied.
Source: PG&amp;E Wholesale Distribution Queue, as dated in the file.</p>
<h2>Official Cluster 16 POI statements</h2>
<p class="sub">Encoded only where a CAISO / PTO notice names the POI. Absence of a row is not availability.
The latest dated statement per POI wins.</p>
{table(avail, ['poi_base', 'utility', 'county', 'c16_poi_status', 'c16_poi_note', 'legacy_active_mw', 'c15_active_mw'],
       links, wrap=('c16_poi_note',))}
"""
    return render("Home", body, "", prov)


def node_page(r: pd.Series, projects: pd.DataFrame, prov: dict, wdat: pd.DataFrame | None = None) -> str:
    title = r.poi_base or r.node_key
    status = str(r.get("c16_poi_status") or "")
    c16 = ""
    if status:
        c16 = (f'<p><b>Official Cluster 16 POI statement: {esc(status)}</b> — {esc(r.get("c16_poi_note", ""))}</p>')
    metrics = "".join(
        f'<tr><td><code>{m}</code></td><td class="num">{fmt(m, r.get(m))}</td><td class="wrap">{esc(d)}</td></tr>'
        for m, d in METRIC_DEFS)
    proj_cols = ["project_name", "queue_position", "sheet_status", "cluster", "net_mw", "storage_mw", "deliverability",
                 "ia_status", "cod", "withdrawn_date"]
    method = str(r.get("geo_method") or "none")
    warn = ""
    if method in APPROX_METHODS:
        if method == "county-centroid":
            why = "position unknown; placed at the median of located nodes in the county"
        elif method == "line-one-end":
            why = "marker sits at one end of a transmission line, not at the tap point"
        elif method == "fuzzy":
            why = "name matched an OpenStreetMap substation only approximately"
        elif method == "ambiguous":
            why = ("several OSM features share this name more than 50 km apart — the position may be the wrong one")
        elif method == "state-mismatch":
            why = ("the matched position was provably outside the filed state and was rejected; this node falls back "
                   "to a county centroid")
        elif method == "override-approx":
            why = "hand-entered approximate coordinate (e.g. plant centroid), not a verified substation position"
        else:
            why = "no position found; this node is not on the map"
        warn = f'<p class="warn">Position is approximate or unknown ({esc(method)}): {why}.</p>'
    lat, lon = r.get("lat"), r.get("lon")
    has_pos = lat is not None and not pd.isna(lat)
    geo = f"""<dl class="kv">
<dt>geo_method</dt><dd>{esc(method)}</dd>
<dt>geo_score</dt><dd>{fmt('geo_score', r.get('geo_score'))}</dd>
<dt>osm_name</dt><dd>{esc(r.get('osm_name', '')) or '—'}</dd>
<dt>lat, lon</dt><dd>{(fmt('lat', lat) + ', ' + fmt('lon', lon)) if has_pos else 'none'}</dd>
</dl>"""
    body = f"""<h1>{esc(title)}</h1>
<p class="sub">{esc(r.county) or 'county unknown'}{(' (' + esc(r.get('state')) + ')') if r.get('state') else ''} ·
{esc(r.utility) or 'utility unknown'} · node key <code>{esc(r.node_key)}</code></p>
{c16}
<h2>Metrics</h2>
<div class="tbl"><table><thead><tr><th>metric</th><th class="num">value</th><th class="wrap">definition</th></tr>
</thead>
<tbody>{metrics}</tbody></table></div>
<h2>Projects at this node ({len(projects)})</h2>
<p class="sub">Both reports. cod = current on-line date (public report) or proposed on-line date (Cluster 15).
ia_status exists only in the public report. Cluster 15 deliverability is requested, not allocated.</p>
{table(projects, proj_cols, wrap=('project_name',))}
{wdat_section(wdat)}
<h2>Geocode provenance</h2>
{warn}
{geo}
"""
    return render(title, body, "../", prov)


def wdat_section(wdat: pd.DataFrame | None) -> str:
    """'WDAT requests at this substation' — only when outputs/wdat_projects.csv exists and has rows for the node."""
    if wdat is None or wdat.empty:
        return ""
    n = len(wdat)
    shown = wdat.head(WDAT_CAP)
    cap = f"<p class=\"sub\">showing {WDAT_CAP} of {n}</p>" if n > WDAT_CAP else ""
    return f"""<h2>WDAT requests at this substation ({n})</h2>
<p class="sub">{esc(WDAT_NOTE)}. WDAT requests connect below CAISO's transmission grid; they carry no CAISO
deliverability unless separately studied.</p>
{cap}{table(shown, WDAT_COLS)}
"""


def load_wdat() -> dict[str, pd.DataFrame]:
    """outputs/wdat_projects.csv grouped by node_key (empty dict when the file is absent)."""
    p = OUT / "wdat_projects.csv"
    if not p.exists():
        return {}
    w = pd.read_csv(p, dtype=str, keep_default_na=False)
    for c in WDAT_COLS + ["node_key", "sheet_status"]:
        if c not in w:
            w[c] = ""
    w["net_mw"] = pd.to_numeric(w["net_mw"], errors="coerce")
    for c in ("request_received", "current_cod"):
        w[c] = w[c].map(date_only)
    w["_o"] = w.sheet_status.map({"ACTIVE": 0, "COMPLETED": 1, "WITHDRAWN": 2}).fillna(3)
    w = w.sort_values(["_o", "net_mw"], ascending=[True, False]).drop(columns="_o")
    return {k: g for k, g in w.groupby("node_key")}


def survival_page(prov: dict) -> str:
    """Kaplan–Meier survival by cluster: inline SVG charts, the summary table and the computed findings.
    Built from outputs/survival_by_cluster.csv + survival_summary.csv (run `caiso-siting survival`)."""
    from . import survival
    long_path, sum_path = OUT / "survival_by_cluster.csv", OUT / "survival_summary.csv"
    if not (long_path.exists() and sum_path.exists()):
        return render("Survival", "<h1>Survival</h1><p>outputs/survival_by_cluster.csv not found; run "
                      "<code>caiso-siting survival</code>.</p>", "", prov)
    long_df = pd.read_csv(long_path)
    summary = pd.read_csv(sum_path)
    clus = long_df[long_df.cohort.isin(survival.CLUSTER_COHORTS)]
    tech = long_df[long_df.cohort.isin(survival.TECH_COHORTS)]
    svg1 = survival.render_svg(clus, adaptive=False)
    svg2 = survival.render_svg(tech, title="C13–C15 by technology: share not yet withdrawn", adaptive=False)
    body = f"""<h1>Queue-cohort survival</h1>
<p class="sub">Kaplan–Meier estimate of the share of each cluster's projects <b>not yet withdrawn</b>, by months since
queue date. Event = withdrawal. Active projects are censored at the CAISO report run date ({esc(prov['run_date'])});
completed projects are censored at their on-line date — completion is success, not an event. S(t) is reported while
at least {survival.MIN_AT_RISK} projects remain at risk. Withdrawal is not failure and the files carry no cause.</p>
<div class="chart">{svg1}</div>
<div class="chart">{svg2}</div>
<h2>Summary</h2>
<p class="sub">s12…s60 = S(t) at 12…60 months; _mw = each project weighted by net MW. n/a = not observed that long.</p>
{md_to_html(survival.summary_markdown(summary))}
<h2>Findings</h2>
<p>{esc(survival.findings(summary))}</p>
<p>Definitions: <code>DATA.md</code> (survival_by_cluster.csv, survival_summary.csv).</p>
"""
    return render("Survival", body, "", prov)


def md_page(title: str, path: Path, fallback: str, prov: dict) -> str:
    if path.exists():
        body = md_to_html(path.read_text(encoding="utf-8"))
    else:
        body = f"<h1>{esc(title)}</h1><p>{esc(fallback)}</p>"
    return render(title, body, "", prov)


# ------------------------------------------------------------------ main

def main() -> None:
    t0 = time.time()
    nodes_path = OUT / "nodes.csv"
    if not nodes_path.exists():
        sys.exit(f"{nodes_path} missing; run `caiso-siting nodes` first")
    nodes = pd.read_csv(nodes_path, dtype={"node_key": str, "poi_base": str, "county": str, "utility": str,
                                           "c16_poi_status": str, "c16_poi_note": str, "osm_name": str,
                                           "geo_method": str, "pipeline_commit": str, "source_run_date": str})
    for c in ("county", "utility", "state", "c16_poi_status", "c16_poi_note", "osm_name", "geo_method", "poi_base"):
        if c not in nodes:
            nodes[c] = ""
        nodes[c] = nodes[c].fillna("")
    projects = load_projects(nodes)
    first = nodes.iloc[0] if len(nodes) else {}
    prov = dict(run_date=esc(first.get("source_run_date", "") or "unknown"),
                commit=esc(first.get("pipeline_commit", "") or "unknown"),
                run=esc(first.get("pipeline_run", "") or "unknown"),
                built=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    wdat_mw = nodes.get("wdat_active_mw", pd.Series(0, index=nodes.index)).fillna(0)
    keep = nodes[(nodes.pipeline_mw > 0) | (nodes.operating_mw > 0) | (wdat_mw > 0)].copy()
    slugs = unique_slugs(keep.node_key.tolist())

    SITE.mkdir(exist_ok=True)
    (SITE / "nodes").mkdir(exist_ok=True)
    for old in (SITE / "nodes").glob("*.html"):      # stale pages from a previous build
        old.unlink()
    (SITE / ".nojekyll").write_text("")

    written = 0
    (SITE / "index.html").write_text(index_page(nodes, projects, slugs, prov), encoding="utf-8")
    written += 1

    by_node = {k: g for k, g in projects.groupby("node_key")} if len(projects) else {}
    wdat_by_node = load_wdat()
    empty = projects.iloc[0:0]
    for r in keep.itertuples(index=False):
        s = pd.Series(r._asdict())
        (SITE / "nodes" / f"{slugs[s.node_key]}.html").write_text(
            node_page(s, by_node.get(s.node_key, empty), prov, wdat_by_node.get(s.node_key)), encoding="utf-8")
        written += 1

    map_src = OUT / "nodes_map.html"
    if map_src.exists():
        shutil.copyfile(map_src, SITE / "map.html")
    else:
        (SITE / "map.html").write_text(render("Map", "<h1>Map</h1><p>outputs/nodes_map.html not found; run "
                                              "<code>caiso-siting nodes</code>.</p>", "", prov), encoding="utf-8")
    written += 1

    (SITE / "diff.html").write_text(md_page("Weekly diff", OUT / "diff_latest.md",
                                            "first diff appears after the second weekly snapshot", prov),
                                    encoding="utf-8")
    written += 1
    (SITE / "note.html").write_text(md_page("Node Watch", OUT / "node_watch.md",
                                            "outputs/node_watch.md not found; run `caiso-siting nodes`.", prov),
                                    encoding="utf-8")
    written += 1
    (SITE / "survival.html").write_text(survival_page(prov), encoding="utf-8")
    written += 1

    print(f"site: {written} pages written to {SITE} ({len(keep)} node pages of {len(nodes)} nodes) "
          f"in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
