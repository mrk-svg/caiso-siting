"""
Document watch — the intake for the prose layer.

CAISO's notices index is JavaScript-rendered (no RSS, not in the sitemap), so instead of scraping it we
watch the server-rendered topic pages that actually carry the documents that change siting decisions,
and report every document link that was not there last week. A human reads each new one and, where it
names a POI, adds a row to data/poi_availability.csv. Nothing is encoded automatically.

    caiso-siting watch            fetch every page in data/watched_pages.txt, diff against data/documents_seen.csv,
                                  write outputs/new_documents.md and append the new ones to documents_seen.csv
    caiso-siting watch --dry-run  report without updating documents_seen.csv

data/watched_pages.txt: one URL per line, '#' comments. Keyword scoring (KEYWORDS) only orders the review
list; it never filters anything out.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from html import unescape
from urllib.parse import urljoin

import pandas as pd

from .config import DATA, OUT

WATCHED = DATA / "watched_pages.txt"
SEEN = DATA / "documents_seen.csv"
DEFAULT_PAGES = [
    "# CAISO pages that carry the documents that change siting decisions (server-rendered; diffed weekly)",
    "https://www.caiso.com/generation-transmission/generation/generator-interconnection",
    "https://www.caiso.com/generation-transmission/generation/generator-interconnection/transmission-plan-deliverability",
    "https://www.caiso.com/generation-transmission/generation/generator-interconnection/interconnection-request-study",
    "https://www.caiso.com/library/interconnection-queue-reports",
    "https://www.caiso.com/library/interconnection-request-and-study",
    "https://www.caiso.com/library/cluster-study-process",
    "https://www.pge.com/en/about/doing-business-with-pge/interconnections/wholesale-generation.html",
    "https://www.sce.com/clean-energy-efficiency/solar-generating-your-own-power/solar-power-basics/grid-interconnections",
]
KEYWORDS = {  # weight: substring (lower-case) in the link text or URL
    5: ["poi availability", "point of interconnection", "cluster 16", "cluster-16", "c16"],
    4: ["deliverability", "tpd", "allocation", "constraint mapping", "constraint-mapping"],
    3: ["cluster 15", "cluster-15", "queue report", "publicqueuereport", "phase i", "phase ii", "restudy", "reassessment"],
    2: ["interconnection", "wdat", "queue", "ipe", "process enhancements"],
    1: ["notice", "briefing", "results"],
}
DOC_RE = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
DOC_EXT = (".pdf", ".xlsx", ".xls", ".docx", ".csv", ".zip")


def score(text: str, url: str) -> int:
    blob = f"{text} {url}".lower()
    return sum(w for w, keys in KEYWORDS.items() for k in keys if k in blob)


def extract_links(html: str, base_url: str) -> list[dict]:
    """Every anchor that points at a document or a CAISO notice/document page."""
    out, seen = [], set()
    for href, inner in DOC_RE.findall(html):
        url = urljoin(base_url, unescape(href.strip()))
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
        low = url.lower()
        if not (low.endswith(DOC_EXT) or "/documents/" in low or "/notices/" in low):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(dict(url=url, text=text[:200], page=base_url, score=score(text, url)))
    return out


def fetch(url: str) -> str:
    import requests
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 (caiso-siting document watch)"})
    r.raise_for_status()
    return r.text


def load_pages() -> list[str]:
    if not WATCHED.exists():
        WATCHED.write_text("\n".join(DEFAULT_PAGES) + "\n")
    return [ln.strip() for ln in WATCHED.read_text().splitlines() if ln.strip() and not ln.startswith("#")]


def load_seen() -> pd.DataFrame:
    if SEEN.exists():
        return pd.read_csv(SEEN, dtype=str)
    return pd.DataFrame(columns=["url", "text", "page", "first_seen", "reviewed", "encoded_in"])


def run(dry_run: bool = False) -> pd.DataFrame:
    OUT.mkdir(exist_ok=True)
    seen = load_seen()
    known = set(seen.url)
    found, failures = [], []
    for page in load_pages():
        try:
            links = extract_links(fetch(page), page)
        except Exception as e:  # noqa: BLE001
            failures.append((page, str(e)))
            continue
        found += links
        print(f"  {page}: {len(links)} document links")
    df = pd.DataFrame(found).drop_duplicates("url") if found else pd.DataFrame(columns=["url", "text", "page", "score"])
    new = df[~df.url.isin(known)].sort_values(["score", "text"], ascending=[False, True])
    today = date.today().isoformat()
    lines = [f"# New documents on watched pages — {today}", "",
             f"{len(new)} new of {len(df)} document links across {len(load_pages())} pages. "
             "Read each; if it names a POI, add a sourced row to data/poi_availability.csv; if it is a queue or TPD "
             "file, refresh data/ and re-run the pipeline. Score orders the list, it filters nothing.", ""]
    if failures:
        lines += ["## Pages that could not be fetched", ""] + [f"- {p}: {e}" for p, e in failures] + [""]
    if len(new):
        lines += ["| score | document | page |", "|---:|---|---|"]
        lines += [f"| {r.score} | [{r.text or r.url.rsplit('/', 1)[-1]}]({r.url}) | {r.page.rsplit('/', 1)[-1]} |"
                  for r in new.itertuples()]
    else:
        lines.append("Nothing new." if not failures else "Nothing new on the pages that could be fetched.")
    (OUT / "new_documents.md").write_text("\n".join(lines) + "\n")
    if not dry_run and len(new):
        add = new[["url", "text", "page"]].copy()
        add["first_seen"] = today
        add["reviewed"] = ""
        add["encoded_in"] = ""
        pd.concat([seen, add], ignore_index=True).to_csv(SEEN, index=False)
    print(f"watch: {len(new)} new documents -> {OUT / 'new_documents.md'}"
          + ("" if dry_run else f"; {SEEN.name} now {len(known) + len(new)} rows"))
    return new


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        run(dry_run=args.dry_run)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
