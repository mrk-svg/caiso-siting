"""Document-watch intake: link extraction, scoring, diffing against the seen list (network mocked)."""
import pandas as pd

from caiso_siting import watch

HTML = """
<html><body>
<a href="/documents/2025-transmission-plan-deliverability-allocation-cycle-results.xlsx">2025 TPD <b>Allocation</b> Results</a>
<a href='https://www.caiso.com/notices/pg-e-information-on-poi-availability-for-cluster-16'>PG&amp;E information on POI availability for Cluster 16</a>
<a href="/about">About</a>
<a href="/documents/engineering-design-plan-form.docx">Engineering Design Plan Form</a>
<a href="/documents/engineering-design-plan-form.docx">duplicate</a>
</body></html>
"""


def test_extract_links_resolves_filters_dedupes():
    links = watch.extract_links(HTML, "https://www.caiso.com/library/x")
    urls = [lk["url"] for lk in links]
    assert urls[0].startswith("https://www.caiso.com/documents/2025-transmission")
    assert "https://www.caiso.com/notices/pg-e-information-on-poi-availability-for-cluster-16" in urls
    assert not any(u.endswith("/about") for u in urls)
    assert urls.count("https://www.caiso.com/documents/engineering-design-plan-form.docx") == 1
    assert links[1]["text"] == "PG&E information on POI availability for Cluster 16"


def test_score_orders_poi_notice_above_forms():
    links = {lk["text"]: lk["score"] for lk in watch.extract_links(HTML, "https://www.caiso.com/")}
    assert links["PG&E information on POI availability for Cluster 16"] > links["2025 TPD Allocation Results"] > links["Engineering Design Plan Form"]


def test_run_diffs_against_seen_and_appends(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "DATA", tmp_path)
    monkeypatch.setattr(watch, "OUT", tmp_path / "out")
    monkeypatch.setattr(watch, "WATCHED", tmp_path / "watched_pages.txt")
    monkeypatch.setattr(watch, "SEEN", tmp_path / "documents_seen.csv")
    (tmp_path / "watched_pages.txt").write_text("# c\nhttps://www.caiso.com/page-a\nhttps://www.caiso.com/page-b\n")
    monkeypatch.setattr(watch, "fetch", lambda url: HTML if url.endswith("page-a") else (_ for _ in ()).throw(RuntimeError("503")))
    pd.DataFrame([dict(url="https://www.caiso.com/documents/engineering-design-plan-form.docx", text="old", page="p",
                       first_seen="2026-01-01", reviewed="", encoded_in="")]).to_csv(tmp_path / "documents_seen.csv", index=False)
    new = watch.run()
    assert len(new) == 2 and "engineering-design" not in " ".join(new.url)
    md = (tmp_path / "out" / "new_documents.md").read_text()
    assert "2 new of 3" in md and "could not be fetched" in md and "page-b" in md
    seen = pd.read_csv(tmp_path / "documents_seen.csv")
    assert len(seen) == 3 and set(seen.columns) >= {"url", "first_seen", "reviewed", "encoded_in"}
    # second run: nothing new, seen unchanged
    assert len(watch.run()) == 0 and len(pd.read_csv(tmp_path / "documents_seen.csv")) == 3


def test_dry_run_does_not_write_seen(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "DATA", tmp_path)
    monkeypatch.setattr(watch, "OUT", tmp_path / "out")
    monkeypatch.setattr(watch, "WATCHED", tmp_path / "watched_pages.txt")
    monkeypatch.setattr(watch, "SEEN", tmp_path / "documents_seen.csv")
    monkeypatch.setattr(watch, "fetch", lambda url: HTML)
    pages = watch.load_pages()          # creates the default watched_pages.txt
    assert len(pages) >= 6 and all(p.startswith("http") for p in pages)
    watch.run(dry_run=True)
    assert not (tmp_path / "documents_seen.csv").exists()
