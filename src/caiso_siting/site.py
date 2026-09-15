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
from .eia860 import EIA_JOIN_KM
from .nodes import APPROX_METHODS, RECENT_FROM_YEAR
from .tpd import GROUPS

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
    ("p2_reached_mw", "MW of projects that received Phase II / Facilities Study results here (public report, any sheet)"),
    ("p2_withdrawn_mw", "of those, MW that then withdrew (== wd_post_phase2_mw)"),
    ("p2_attrition", "p2_withdrawn_mw / p2_reached_mw — share of studied MW that left with results in hand"),
    ("committed_mw", "ACTIVE MW holding an executed interconnection agreement (public report)"),
    ("churn_n", "projects behind storage_churn (withdrawn recent + queued + operating)"),
    ("c15_n", "projects behind c15_survival"),
    ("p2_n", "projects behind p2_attrition"),
    ("eia_plants", "operable EIA-860 plants within 5 km of the node's mapped position (positioned nodes only)"),
    ("eia_nameplate_mw", "their nameplate MW, all technologies (EIA-860 Generator file, Operable sheet)"),
    ("eia_storage_mwh", "battery energy capacity among them (EIA-860 Energy Storage file)"),
    ("eia_proposed_mw", "nameplate MW in EIA-860's Proposed sheet within the same radius (planned / under construction)"),
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
    ("tpd25_req_A_mw", "of tpd25_req_mw, requested in allocation group A: executed PPA (or LSE own load)"),
    ("tpd25_req_B_mw", "of tpd25_req_mw, requested in allocation group B: shortlisted / negotiating a PPA"),
    ("tpd25_req_C_mw", "of tpd25_req_mw, requested in allocation group C: already in commercial operation"),
    ("tpd25_req_D_mw", "of tpd25_req_mw, requested in allocation group D: no PPA, Section 8.9.2.3 path"),
    ("tpd25_denied_A_mw", "of tpd25_denied_mw, refused at 0 % in group A"),
    ("tpd25_denied_B_mw", "of tpd25_denied_mw, refused at 0 % in group B"),
    ("tpd25_denied_C_mw", "of tpd25_denied_mw, refused at 0 % in group C"),
    ("tpd25_denied_D_mw", "of tpd25_denied_mw, refused at 0 % in group D"),
    ("tpd25_denied_ppa_mw", "refused MW in groups A + B: contracted or shortlisted projects that did not get "
                            "deliverability; the refusal that matters"),
    ("tpd24_fcdsa_projects", "projects at the node allocated Full Capacity in the 2024 cycle"),
    ("lcr_status", "CAISO Local Capacity Area (Resource Adequacy geography): 'in <area>' or 'outside <area>' as the "
                   "LCT report's boundary lists state it; blank = not encoded, never 'outside every area'"),
    ("lcr_sub_area", "sub-area / load pocket within that area, when the LCT report delineates it"),
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
            "wd_recent_mw", "storage_churn", "c15_survival", "p2_attrition", "tpd25_denied_ppa_mw", "lcr_status",
            "c16_poi_status"]

CSS = """
:root{--fg:#1b1b1b;--muted:#5b5b5b;--bg:#f6f6f2;--line:#dcdcd6;--card:#fff;--accent:#1d4ed8;--warn:#9a3412;--warnbg:#fff4ec;
  --ok:#0f6b3f;--okbg:#eaf6ef;--dim:#8a8a84;--th:#f1f1ec;--code:#eeeee8;--np:#6b5d00;--npbg:#fdf6d8}
@media (prefers-color-scheme:dark){:root{--fg:#e8e8e3;--muted:#a7a7a0;--bg:#121311;--line:#2e2f2b;--card:#1b1c19;
  --accent:#8ab4f8;--warn:#f0a070;--warnbg:#2a1d14;--ok:#7fd3a5;--okbg:#14261c;--dim:#6f6f69;--th:#22231f;--code:#26271f;
  --np:#e6cf6a;--npbg:#2a2510}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{border-bottom:1px solid var(--line);background:var(--card)}
header .in{max-width:1180px;margin:0 auto;padding:10px 16px;display:flex;flex-wrap:wrap;gap:6px 18px;align-items:baseline}
header .brand{font-weight:700;margin-right:auto}
header nav a{white-space:nowrap}
main{max-width:1180px;margin:0 auto;padding:16px}
h1{font-size:1.7rem;margin:.2em 0 .25em;letter-spacing:-.01em}
h2{font-size:1.2rem;margin:1.5em 0 .5em;border-bottom:1px solid var(--line);padding-bottom:.25em}
h3{font-size:1.02rem;margin:1em 0 .3em}
.sub{color:var(--muted);margin:0 0 .8em}
.disclaimer{background:var(--warnbg);border-left:4px solid var(--warn);padding:8px 12px;margin:12px 0;font-size:.92rem}
.warn{color:var(--warn);font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:14px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile .n{font-size:1.5rem;font-weight:700;line-height:1.15}.tile .l{color:var(--muted);font-size:.85rem}
.tbl{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0 16px}
table{border-collapse:collapse;width:100%;font-size:.9rem;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}
th{background:var(--th);position:sticky;top:0}
td.num,th.num{text-align:right}
tr:last-child td{border-bottom:0}
td.wrap,th.wrap{white-space:normal;min-width:16em}
dl.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:8px 0}
dl.kv dt{font-weight:600}dl.kv dd{margin:0}
.md table{width:auto}
.chart{max-width:760px;margin:12px 0}.chart svg{width:100%;height:auto;display:block}
.md pre,.md code,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em}
.md code,code{background:var(--code);padding:1px 4px;border-radius:3px}
/* node page: seven questions */
.qs{counter-reset:q}
.q{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px 10px;margin:14px 0}
.q h2{border:0;margin:0 0 .4em;padding:0;font-size:1.15rem}
.q h2::before{counter-increment:q;content:counter(q) ". ";color:var(--muted)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px 14px;margin:6px 0 10px}
.fact{padding:6px 0}
.fact .v{font-size:1.25rem;font-weight:700;line-height:1.2}.fact .k{color:var(--muted);font-size:.82rem}
.fact .n{color:var(--muted);font-size:.8rem;font-weight:400}
.fact.dim .v{color:var(--dim);font-weight:500}
.fact.dim .k::after{content:" — too few projects to read as a rate"}
.fact.undefined .v{color:var(--dim);font-weight:500}
.fact.undefined .k::after{content:" — no denominator at this node"}
.np{background:var(--npbg);color:var(--np);border-left:3px solid var(--np);padding:6px 10px;margin:8px 0;font-size:.9rem;border-radius:0 6px 6px 0}
.np b{font-weight:700}
.np.soft{background:transparent;border-left-color:var(--line);color:var(--muted)}
.ok{background:var(--okbg);color:var(--ok);border-left:3px solid var(--ok);padding:6px 10px;margin:8px 0;font-size:.92rem;border-radius:0 6px 6px 0}
.q p.sub{margin:.2em 0 .6em}
.badge{display:inline-block;font-size:.78rem;padding:1px 8px;border:1px solid var(--line);border-radius:999px;color:var(--muted);margin-left:6px;vertical-align:middle}
footer{max-width:1180px;margin:24px auto 40px;padding:12px 16px;border-top:1px solid var(--line);color:var(--muted);font-size:.85rem}
footer p{margin:.3em 0}
@media (max-width:600px){body{font-size:14px}main{padding:10px}th,td{padding:5px 7px}.q{padding:12px 12px 8px}}
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
<a href="${root}diff.html">Weekly diff</a> · <a href="${root}methodology.html">Methodology</a></nav>
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
        return "n/a" if col in ("storage_churn", "churn_alltime", "c15_survival", "geo_score", "p2_attrition") else ""
    if (col.endswith(("_mw", "_mwh", "_projects", "_plants", "_n")) or col in ("mw_requested", "mw_allocated")
            or col == "eia_first_year"):
        return f"{float(v):,.0f}"
    if col in ("storage_churn", "churn_alltime", "c15_survival", "geo_score", "p2_attrition"):
        return f"{float(v):.2f}"
    if col == "allocation_pct":
        return f"{float(v):.0%}"
    if col == "tpd_year":
        return esc(str(v).split(".")[0])
    if col in ("lat", "lon"):
        return f"{float(v):.5f}"
    return esc(v)


def is_num(col: str) -> bool:
    return col.endswith(("_mw", "_projects", "_n")) or col in ("storage_churn", "churn_alltime", "c15_survival", "geo_score", "lat", "lon", "p2_attrition",
                                          "queue_position", "allocation_pct", "tpd_year", "queue_id", "mw_requested", "mw_allocated")


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
    (re.compile(r"\[([^\]]+)\]\((https?://[^)\s\"'<>]+)\)"), r'<a href="\2">\1</a>'),
]


def _inline(s: str) -> str:
    s = html.escape(s, quote=True)
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
    group_legend = "; ".join(f"{g} = {esc(d)}" for g, d in GROUPS.items())
    body = f"""<h1>CAISO interconnection nodes</h1>
<p class="sub">Public Queue Report + Cluster 15 report, unified per point of interconnection, joined to official
Cluster 16 POI statements. CAISO report run date {esc(prov['run_date'])}. Every number traces to a CAISO row.</p>
<div class="tiles">{tiles}</div>
<p><a href="map.html">Map</a> (size = pipeline MW, fill = storage churn) ·
<a href="diff.html">Weekly diff</a> · <a href="note.html">Node Watch note</a> ·
<a href="survival.html">Survival by cluster</a> · {n_pages} node pages.</p>
<h2>Top 40 nodes by pipeline MW (legacy active + Cluster 15 active)</h2>
<p class="sub">storage_churn = storage MW withdrawn in the last {RECENT_YEARS} years ÷ (active + operating storage MW).
c15_survival = C15 active ÷ (C15 active + C15 withdrawn). lcr_status = CAISO Local Capacity Area (Resource Adequacy
geography) as the 2027 Local Capacity Technical Report's boundary lists state it — "in" or "outside" a named area;
blank means the report does not name the station, not "outside every area".
Click a node for its projects and geocode provenance.</p>
{table(top, TOP_COLS, links)}
<h2>TPD allocation, 2025 cycle</h2>
<p class="sub">Top 15 nodes by MW that sought Transmission Plan Deliverability in CAISO's 2025 allocation cycle.</p>
{table(tpd, ['poi_base', 'county', 'utility', 'tpd25_req_mw', 'tpd25_alloc_mw', 'tpd25_unalloc_mw',
             'tpd25_denied_mw', 'tpd25_denied_ppa_mw', 'tpd25_denied_D_mw', 'tpd24_fcdsa_projects'], links)}
<p>"Denied" is MW refused outright (0 %); "unalloc" is requested minus allocated, so it also carries the remainder
left by partial allocations. A refusal is not one thing: CAISO allocates by group — {group_legend}. A 0 % in
group D is the expected result for an uncontracted project; a 0 % in group A or B (<code>tpd25_denied_ppa_mw</code>)
is a contracted or shortlisted project that did not get deliverability, and is the number to quote. These rows are
joined through all three sheets of the public report, so a node's TPD history can include requests whose project has
since withdrawn. The CAISO file states no reason.</p>
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


MIN_N = 3          # ratios built on fewer projects than this are shown dimmed
MIN_DENOM_MW = 500  # ... or on a denominator smaller than this


def fact(label: str, value: str, n: int | None = None, dim: bool = False, note: str = "",
         undefined: bool = False) -> str:
    """One figure with its label; `dim` = too few projects behind a ratio; `undefined` = a ratio with no
    denominator (shown as n/a, no small-n reason attached)."""
    nn = f' <span class="n">(n={n})</span>' if n is not None else ""
    cls = " undefined" if undefined else (" dim" if dim else "")
    return (f'<div class="fact{cls}"><div class="v">{esc(value)}{nn}</div>'
            f'<div class="k">{esc(label)}{(" · " + esc(note)) if note else ""}</div></div>')


def mw(v) -> str:
    try:
        return f"{float(v):,.0f} MW"
    except (TypeError, ValueError):
        return "0 MW"


def ratio(v, n: int, denom_mw: float) -> tuple[str, bool, bool]:
    """(text, dim, undefined): undefined when there is no denominator; dim when too few projects support it."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a", False, True
    return f"{float(v):.2f}", (n < MIN_N or denom_mw < MIN_DENOM_MW), False


def not_public(what: str, where: str) -> str:
    return f'<div class="np"><b>Not public:</b> {esc(what)} — {esc(where)}</div>'


def not_here_yet(what: str, where: str) -> str:
    """Public, but not on this site yet — never dressed up as 'not public'."""
    return f'<div class="np soft"><b>Not on this site yet:</b> {esc(what)} — {esc(where)}</div>'


def node_page(r: pd.Series, projects: pd.DataFrame, prov: dict, wdat: pd.DataFrame | None = None,
              tpd_rows: pd.DataFrame | None = None) -> str:
    """One node, read top to bottom before filing: seven questions, each answered with the sourced figure, the
    count behind it, and a 'not public' line where the truth is that the answer is behind a login."""
    g = lambda k, d=0: r.get(k, d) if not (isinstance(r.get(k, d), float) and pd.isna(r.get(k, d))) else d
    title = r.poi_base or r.node_key
    active = projects[projects.sheet_status == "ACTIVE"] if len(projects) else projects
    ahead_mw = float(g("legacy_active_mw")) + float(g("c15_active_mw"))
    ahead_n = int(g("legacy_active_projects")) + int(g("c15_active_projects"))

    # --- 1. can you get in
    status = str(g("c16_poi_status", "") or "")
    if status:
        q1 = (f'<div class="ok"><b>Official Cluster 16 POI statement: {esc(status)}</b> — '
              f'{esc(g("c16_poi_note", ""))}</div>')
    else:
        q1 = ('<p class="sub">No official Cluster 16 availability statement names this POI. Absence of a statement '
              'is not availability.</p>')
    q1 += not_public("per-constraint transmission headroom at this POI",
                     "CAISO's cluster study reports (RIMS login).")
    q1 += not_here_yet("the zonal transmission-capability table CAISO publishes for cluster scoring",
                       "public; the join is planned.")

    # --- 2. who is ahead
    q2 = '<div class="facts">' + "".join([
        fact("queued ahead of a new request (legacy + C15)", mw(ahead_mw), ahead_n),
        fact("with an executed interconnection agreement", mw(g("committed_mw")), int(g("committed_projects")),
             note="public report; C15 has no IA yet"),
        fact("operating at this node", mw(g("operating_mw")), int(g("operating_projects"))),
        fact("Cluster 15 requests seeking full capacity", mw(g("c15_fcds_req_mw"))),
    ]) + "</div>"
    eia_n = int(g("eia_plants"))
    if eia_n:
        yr = g("eia_first_year", float("nan"))
        parts = [f"{eia_n} plant{'s' if eia_n != 1 else ''}", f"{mw(g('eia_nameplate_mw'))} nameplate"]
        smwh = float(g("eia_storage_mwh"))
        if smwh > 0:
            parts.append(f"{mw(g('eia_storage_mw'))} / {smwh:,.0f} MWh storage")
        if isinstance(yr, (int, float)) and not pd.isna(yr):
            parts.append(f"oldest unit {int(yr)}")
        prop = float(g("eia_proposed_mw"))
        if prop > 0:
            parts.append(f"{prop:,.0f} MW proposed")
        extra = ""
        for label, key, code in (("Technology", "eia_tech", False), ("Operators", "eia_operators", False),
                                 ("Owners", "eia_owners", False), ("LMP nodes reported by these generators", "eia_pnodes", True)):
            val = str(g(key, "") or "")
            if val:
                extra += f" {label}: " + (f"<code>{esc(val)}</code>" if code else esc(val)) + "."
        q2 += (f'<div class="ok"><b>Already operating within {int(EIA_JOIN_KM)} km (EIA-860):</b> {"; ".join(parts)}.'
               f'{extra} <span class="sub">Joined by distance to this node\'s mapped position, not by point of '
               f'interconnection: a plant on a long gen-tie lands on the nearest substation. Corporate names from a '
               f'federal filing.</span></div>')
    q2 += not_public("who the interconnection customers are (the queue)",
                     "CAISO's public files carry project names only; the projects table below is the full public record. "
                     "EIA-860 names the owners of what already operates nearby, not of what is queued.")

    # --- 3. do they leave after seeing costs
    p2n, p2r = int(g("p2_n")), float(g("p2_reached_mw"))
    p2v, p2dim, p2und = ratio(g("p2_attrition", float("nan")), p2n, p2r)
    q3 = '<div class="facts">' + "".join([
        fact("received Phase II / Facilities Study results here", mw(p2r), p2n, note="any sheet, public report"),
        fact("of that, withdrew with results in hand", mw(g("p2_withdrawn_mw")), int(g("p2_withdrawn_projects"))),
        fact("Phase II attrition (MW share)", p2v, p2n, dim=p2dim, undefined=p2und),
    ]) + "</div>"
    q3 += not_public("the network upgrade cost allocated to a project here",
                     "Phase I / Phase II study reports, served through RIMS. Ask the incumbent developer or request "
                     "the report; nothing public reconstructs it.")

    # --- 4. deliverability
    req, alloc = float(g("tpd25_req_mw")), float(g("tpd25_alloc_mw"))
    q4 = '<div class="facts">' + "".join([
        fact("2025 TPD requested at this node", mw(req), int(g("tpd25_projects"))),
        fact("allocated", mw(alloc)),
        fact("refused at 0 % — contracted / shortlisted (groups A+B)", mw(g("tpd25_denied_ppa_mw"))),
        fact("refused at 0 % — no PPA (group D)", mw(g("tpd25_denied_D_mw"))),
        fact("2024 cycle: projects given full / partial capacity",
             f"{int(g('tpd24_fcdsa_projects'))} / {int(g('tpd24_pcdsa_projects'))}"),
    ]) + "</div>"
    if req == 0:
        q4 += '<p class="sub">No request from this node appears in the 2025 allocation results.</p>'
    q4 += ('<p class="sub">A 0 % in group D is the expected result for an uncontracted project; a 0 % in group A or B '
           'is a contracted project that did not get deliverability. Rows are joined through all three sheets, so a '
           'request whose project has since withdrawn still appears. CAISO states no reason.</p>')

    # --- 5. worth anything
    lcr_status = str(g("lcr_status", "") or "")
    if lcr_status.startswith("in "):
        sub = str(g("lcr_sub_area", "") or "")
        q5 = (f'<div class="ok"><b>Local Capacity Area: {esc(g("lcr_area"))}</b>'
              f'{(" · sub-area " + esc(sub)) if sub else ""}'
              f'{(" — " + esc(g("lcr_note"))) if g("lcr_note", "") else ""} '
              f'<span class="badge">{esc(g("lcr_source", ""))}</span></div>')
    elif lcr_status.startswith("outside"):
        q5 = (f'<div class="np"><b>{esc(lcr_status[0].upper() + lcr_status[1:])} local area boundary</b>'
              f'{(" — " + esc(g("lcr_note"))) if g("lcr_note", "") else ""} '
              f'<span class="badge">{esc(g("lcr_source", ""))}</span></div>')
    else:
        q5 = ('<p class="sub">The Local Capacity Technical Report does not name this substation on any area boundary: '
              'not encoded, which is not the same as outside every area.</p>')
    lmp = g("lmp_tb4_12mo_mean", float("nan"))
    if isinstance(lmp, (int, float)) and not pd.isna(lmp):
        q5 += '<div class="facts">' + fact("day-ahead TB4 spread, 12-month mean ($/MWh)", f"{float(lmp):,.1f}",
                                           note=f"{int(g('lmp_months', 0))} months") + "</div>"
    else:
        q5 += not_here_yet("day-ahead price history at this POI",
                           "CAISO OASIS publishes it; it is shown only for a pricing node confirmed by hand in "
                           "data/poi_pnodes.csv, and this one is not confirmed yet.")

    # --- 6. will the land pass
    q6 = ('<p class="sub">Intake scoring under the 2023 IPE rewards site control, permitting progress and system need '
          'before study begins. Parcel, zoning, Williamson Act and CEC exclusion screens run for Kings and Kern counties '
          '(<code>caiso-siting parcels</code>, <code>layers screen</code>); results are in <code>outputs/parcels_*.md</code> '
          'for the nodes they were run on and are not yet rendered per node here.</p>')
    q6 += not_public("landowner willingness and option terms",
                     "county assessor parcels give ownership class, not intent; owner names are withheld on purpose.")

    # --- 7. how long
    cn, sc = int(g("churn_n")), g("storage_churn", float("nan"))
    scv, scdim, scund = ratio(sc, cn, float(g("pipeline_storage_mw")) + float(g("operating_storage_mw")))
    c15n = int(g("c15_n"))
    sv, svdim, svund = ratio(g("c15_survival", float("nan")), c15n,
                             float(g("c15_active_mw")) + float(g("c15_withdrawn_mw")))
    cods = sorted(c for c in active.cod.tolist() if c) if len(active) else []
    cod_txt = (cods[0] if cods[0] == cods[-1] else f"{cods[0]} to {cods[-1]}") if cods else "none active"
    q7 = '<div class="facts">' + "".join([
        fact(f"withdrawn since {RECENT_FROM_YEAR} (both reports)", mw(g("wd_recent_mw")), int(g("wd_recent_projects"))),
        fact("of that, storage", mw(g("wd_recent_storage_mw"))),
        fact("storage churn", scv, cn, dim=scdim, undefined=scund, note="withdrawn storage ÷ queued + operating storage"),
        fact("Cluster 15 survival", sv, c15n, dim=svdim, undefined=svund, note="active ÷ (active + withdrawn)"),
        fact("all-time withdrawn since 2006", mw(g("wd_alltime_mw")), int(g("wd_alltime_projects")),
             note="mostly wind/solar-era; colour, not signal"),
        fact("current on-line dates of active projects", cod_txt),
    ]) + "</div>"
    q7 += ('<p class="sub">Cluster-level time-to-withdrawal curves are on the <a href="../survival.html">Survival</a> '
           'page; they compare process regimes, not only nodes.</p>')

    proj_cols = ["project_name", "queue_position", "sheet_status", "cluster", "net_mw", "storage_mw", "deliverability",
                 "ia_status", "cod", "withdrawn_date"]
    method = str(g("geo_method", "") or "none")
    warn = ""
    if method in APPROX_METHODS:
        why = {
            "county-centroid": "position unknown; placed at the median of located nodes in the county",
            "line-one-end": "marker sits at one end of a transmission line, not at the tap point",
            "line-midpoint": "marker sits at the midpoint between the line's two named ends, which is not a place",
            "fuzzy": "name matched an OpenStreetMap substation only approximately",
            "ambiguous": "several OSM features share this name more than 50 km apart — the position may be the wrong one",
            "state-mismatch": "the matched position was provably outside the filed state and was rejected; this node "
                              "falls back to a county centroid",
            "override-approx": "hand-entered approximate coordinate (e.g. plant centroid), not a verified substation position",
        }.get(method, "no position found; this node is not on the map")
        warn = f'<p class="warn">Position is approximate or unknown ({esc(method)}): {why}.</p>'
    lat, lon = g("lat", None), g("lon", None)
    has_pos = lat is not None and lat != 0 and not pd.isna(lat)
    geo = f"""<dl class="kv">
<dt>geo_method</dt><dd>{esc(method)}</dd>
<dt>geo_score</dt><dd>{fmt('geo_score', g('geo_score', None))}</dd>
<dt>osm_name</dt><dd>{esc(g('osm_name', '')) or '—'}</dd>
<dt>lat, lon</dt><dd>{(fmt('lat', lat) + ', ' + fmt('lon', lon)) if has_pos else 'none'}</dd>
</dl>"""
    body = f"""<h1>{esc(title)}</h1>
<p class="sub">{esc(r.county) or 'county unknown'}{(' (' + esc(g('state')) + ')') if g('state', '') else ''} ·
{esc(r.utility) or 'utility unknown'} · node key <code>{esc(r.node_key)}</code> · CAISO run date {esc(prov['run_date'])}</p>
<p class="sub">Seven questions a developer, lender or counsel asks before filing here. Every figure is a CAISO row;
<b>Not public</b> marks what the public files cannot answer and where to get it. Definitions:
<a href="../methodology.html">methodology</a>.</p>
<div class="qs">
<section class="q"><h2>Can you get in?</h2>{q1}</section>
<section class="q"><h2>Who is ahead of you?</h2>{q2}</section>
<section class="q"><h2>Do projects leave after seeing the costs?</h2>{q3}</section>
<section class="q"><h2>Will you be deliverable?</h2>{q4}</section>
<section class="q"><h2>Will the power be worth anything here?</h2>{q5}</section>
<section class="q"><h2>Will the land pass intake?</h2>{q6}</section>
<section class="q"><h2>How long, and who gave up?</h2>{q7}</section>
</div>
<h2>Projects at this node ({len(projects)})</h2>
<p class="sub">Both reports. cod = current on-line date (public report) or proposed on-line date (Cluster 15).
ia_status exists only in the public report. Cluster 15 deliverability is requested, not allocated.</p>
{table(projects, proj_cols, wrap=('project_name',))}
{tpd_section(tpd_rows)}
{wdat_section(wdat)}
<h2>Geocode provenance</h2>
{warn}
{geo}
<h2>All metrics</h2>
<div class="tbl"><table><thead><tr><th>metric</th><th class="num">value</th><th class="wrap">definition</th></tr></thead>
<tbody>{"".join(f'<tr><td><code>{m}</code></td><td class="num">{fmt(m, r.get(m))}</td><td class="wrap">{esc(d)}</td></tr>' for m, d in METRIC_DEFS)}</tbody></table></div>
"""
    return render(title, body, "../", prov)


TPD_ROW_COLS = ["tpd_year", "queue_id", "project_name", "allocation_group", "mw_requested", "allocation_pct",
                "mw_allocated", "status"]


def tpd_section(rows: pd.DataFrame | None) -> str:
    """'TPD allocation requests at this node' — one row per request in CAISO's 2024/2025 results, with the
    allocation group, so a reader can see whether a 0 % landed on a contracted (A/B) or uncontracted (D) project."""
    if rows is None or rows.empty:
        return ""
    legend = "; ".join(f"{g} = {esc(d)}" for g, d in GROUPS.items())
    return f"""<h2>TPD allocation requests at this node ({len(rows)})</h2>
<p class="sub">CAISO Transmission Plan Deliverability allocation results, joined on queue position through all three
sheets of the public report (a request whose project has since withdrawn still appears). 2024 rows carry no MW.
Groups: {legend}.</p>
{table(rows, TPD_ROW_COLS, wrap=('project_name',))}
"""


def load_tpd_rows() -> dict[str, pd.DataFrame]:
    """outputs/tpd_node_rows.csv grouped by node_key (empty dict when the file is absent)."""
    p = OUT / "tpd_node_rows.csv"
    if not p.exists():
        return {}
    t = pd.read_csv(p, dtype=str, keep_default_na=False)
    for c in TPD_ROW_COLS + ["node_key"]:
        if c not in t:
            t[c] = ""
    for c in ("mw_requested", "mw_allocated", "allocation_pct"):
        t[c] = pd.to_numeric(t[c], errors="coerce")
    t = t.sort_values(["tpd_year", "allocation_group", "queue_id"], ascending=[False, True, True])
    return {k: g for k, g in t.groupby("node_key")}


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
<h2>Process regime by cohort</h2>
<p class="sub">Read the curves against this table. A cohort that had to score, pay more, or prove site control to be in
the queue at all will withdraw less for that reason alone.</p>
{md_to_html(survival.regimes_markdown())}
<p>Definitions: <code>DATA.md</code> (survival_by_cluster.csv, survival_summary.csv).</p>
"""
    return render("Survival", body, "", prov)


NOT_PUBLIC = [
    ("Network upgrade cost per project", "Phase I / Phase II cluster study reports, served through CAISO's RIMS login."),
    ("Per-constraint transmission headroom", "the same study reports; CAISO's zonal transmission-capability table is the "
                                             "public proxy used for cluster scoring."),
    ("Interconnection customer identity", "not in the Public Queue Report or the Cluster 15 report; project names only."),
    ("Interconnection financial security posted", "computed per project from non-public study costs; no public $/MW rate "
                                                  "reconstructs it."),
    ("Why a project withdrew", "the files carry no reason beyond the withdrawal date."),
    ("Begin-construction status (tax credit eligibility)", "not a CAISO data element."),
    ("Landowner willingness", "assessor parcels give ownership class; owner names are withheld on purpose."),
    ("Load-side interconnection", "data-center and other load requests are a utility process with no public queue."),
]


def methodology_page(prov: dict) -> str:
    from .config import RECENT_YEARS as RY
    from .survival import C15_CENSOR_DATE, MIN_AT_RISK, REGIME_CAVEAT
    defs = "".join(f'<tr><td><code>{m}</code></td><td class="wrap">{esc(d)}</td></tr>' for m, d in METRIC_DEFS)
    npub = "".join(f'<tr><td class="wrap"><b>{esc(a)}</b></td><td class="wrap">{esc(b)}</td></tr>' for a, b in NOT_PUBLIC)
    body = f"""<h1>Methodology</h1>
<p class="sub">Everything on this site is a deterministic transform of a public file. This page states the sources,
the node definition, every window and exclusion, every metric, and the list of things the public files cannot answer.
An auditor should be able to reproduce any figure from this page and <code>DATA.md</code> without reading code.</p>

<h2>Sources</h2>
<p>CAISO Public Queue Report (three sheets: active, completed, withdrawn; report run date {esc(prov['run_date'])}).
CAISO Cluster 15 Interconnection Requests report (active + withdrawn sheets; posted {C15_CENSOR_DATE}). CAISO 2024 and
2025 Transmission Plan Deliverability allocation cycle results. CAISO 2025 TPD Allocation Report (group definitions,
2026-04-13). CAISO Final 2027 Local Capacity Technical Report (area boundary substations, 2026-04-29). CAISO and PTO
notices on Cluster 16 POI availability, encoded only where a notice names the POI. PG&amp;E Wholesale Distribution
(WDAT) public queue. OpenStreetMap substations (ODbL) for positions. Kings and Kern county GIS and CEC open data for
land screens. Licences and attribution: <code>DATA_LICENSES.md</code>.</p>

<h2>What a node is</h2>
<p>A node is CAISO's free-text point of interconnection normalised: upper-cased, voltage tokens, "SUBSTATION" /
"SWITCHING STATION" and circuit suffixes (#1, #2) removed, line POIs split at the hyphen. Two consequences to keep in
mind: a station's 230 kV and 500 kV yards are one node here even though they are different constraints, and a
same-name station in two utilities can collide (utility is used to separate them where a source names it).</p>

<h2>Windows, censoring, exclusions</h2>
<p>"Recent" means withdrawn in the last {RY} calendar years including the current one, i.e. from
{RECENT_FROM_YEAR}. Storage MW per project is the sum of its storage components capped at its net-to-grid figure.
Survival curves: event = withdrawal at <code>withdrawn_date</code>; active projects censored at the public report run
date; completed projects censored at their on-line date (completion is success, not an event); Cluster 15 censored at
its posting date {C15_CENSOR_DATE}, or at the latest withdrawal the file records if CAISO has re-posted it since; a cohort's S(t) is reported only while at least {MIN_AT_RISK} projects remain at risk; rows with a
withdrawal before their queue date, or no queue date, are excluded and counted.</p>
<p>{esc(REGIME_CAVEAT)}</p>

<h2>Ratios and small numbers</h2>
<p>Every ratio on a node page carries the count of projects behind it. A ratio built on fewer than {MIN_N} projects or
on a denominator under {MIN_DENOM_MW:,} MW is shown dimmed: it is arithmetically correct and statistically empty
(a node with one withdrawal and one survivor has a churn of 1.00 or 3.33 or 0.10 depending on their sizes, and none of
those numbers describes the node).</p>

<h2>Metric definitions</h2>
<div class="tbl"><table><thead><tr><th>metric</th><th class="wrap">definition</th></tr></thead><tbody>{defs}</tbody></table></div>

<h2>What the public files cannot answer</h2>
<p>These are stated on every node page as <b>Not public</b>. They are the questions a developer must pay for, ask for,
or accept as unknown — knowing which is which is most of the diligence.</p>
<div class="tbl"><table><thead><tr><th class="wrap">question</th><th class="wrap">where the answer lives</th></tr></thead><tbody>{npub}</tbody></table></div>

<h2>What this site never does</h2>
<p>No composite score. No cause attributed to a withdrawal. No dollar figure that is not in a source. No per-project
prediction. No names of private individuals: parcel owners are never read, and an EIA-860 owner or operator that reads as a person is counted, not named. No figure generated by a language model: the pipeline is deterministic
Python, the code is public, and every output row carries the source file, the source run date and the pipeline commit.</p>

<h2>Update cadence</h2>
<p>A GitHub Actions job runs every Monday: it downloads CAISO's current files, rebuilds everything, and commits a dated
snapshot, opens a row-level diff issue only when CAISO's report run date is new; the site itself is redeployed on every run.</p>
"""
    return render("Methodology", body, "", prov)


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
    for c in ("county", "utility", "state", "c16_poi_status", "c16_poi_note", "osm_name", "geo_method", "poi_base",
              "lcr_area", "lcr_sub_area", "lcr_status", "lcr_note", "lcr_source",
              "eia_tech", "eia_operators", "eia_owners", "eia_pnodes"):
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
    (SITE / "methodology.html").write_text(methodology_page(prov), encoding="utf-8")
    written += 2

    by_node = {k: g for k, g in projects.groupby("node_key")} if len(projects) else {}
    wdat_by_node = load_wdat()
    tpd_by_node = load_tpd_rows()
    empty = projects.iloc[0:0]
    for r in keep.itertuples(index=False):
        s = pd.Series(r._asdict())
        (SITE / "nodes" / f"{slugs[s.node_key]}.html").write_text(
            node_page(s, by_node.get(s.node_key, empty), prov, wdat_by_node.get(s.node_key),
                      tpd_by_node.get(s.node_key)), encoding="utf-8")
        written += 1

    map_src = OUT / "nodes_map.html"
    if map_src.exists():
        # the site serves its own Leaflet (BSD-2, src/caiso_siting/vendor) so the map never depends on a CDN;
        # outputs/nodes_map.html keeps the CDN+SRI tags so it still works as a standalone file
        vendor = Path(__file__).parent / "vendor"
        (SITE / "vendor").mkdir(exist_ok=True)
        for f in ("leaflet.js", "leaflet.css", "LICENSE-leaflet.txt"):
            if (vendor / f).exists():
                shutil.copyfile(vendor / f, SITE / "vendor" / f)
        map_html = map_src.read_text(encoding="utf-8")
        if (vendor / "leaflet.js").exists() and (vendor / "leaflet.css").exists():
            map_html = re.sub(r'<link rel="stylesheet" href="https://unpkg\.com/leaflet@[^"]+/leaflet\.css"[^>]*>',
                              '<link rel="stylesheet" href="vendor/leaflet.css">', map_html)
            map_html = re.sub(r'<script src="https://unpkg\.com/leaflet@[^"]+/leaflet\.js"[^>]*></script>',
                              '<script src="vendor/leaflet.js"></script>', map_html)
        else:
            print(f"warning: {vendor} has no leaflet.js/leaflet.css — map.html keeps the CDN tags", file=sys.stderr)
        (SITE / "map.html").write_text(map_html, encoding="utf-8")
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
