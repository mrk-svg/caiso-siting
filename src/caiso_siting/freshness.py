"""Is each source current enough to publish?

The rule this module enforces, in the owner's words: *if you can't find the data, or it's expired,
don't use it*. The trap is that "expired" is not "not today's". CAISO publishes the Local Capacity
Technical Report once a year, so it is *supposed* to be eleven months old for most of the year; PG&E
posts its WDAT queue monthly, so a two-month-old copy is genuinely stale. Every threshold here is
therefore measured against the source's own cadence, recorded per source in
`data/source_freshness.csv`.

Before this existed, a missing source published as the number zero. Delete `data/eia860.zip` and
every node reported `eia_nameplate_mw = 0.0`, which a reader parses as "nothing operates near this
node" rather than "we do not know". That is the failure this module is built to stop.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .config import DATA, OUT, xlsx_run_date

REGISTRY = DATA / "source_freshness.csv"
ROOT = DATA.parent

FRESH, STALE, EXPIRED, UNDATED, MISSING = "FRESH", "STALE", "EXPIRED", "UNDATED", "MISSING"


class SourceExpired(RuntimeError):
    """A source the pipeline cannot honestly publish without."""


@dataclass(frozen=True)
class SourceStatus:
    source_id: str
    label: str
    artifact: str
    cadence: str
    published: str
    vintage: str
    age_days: int | None
    severity: str
    on_expired: str
    note: str
    feeds: tuple[str, ...] = field(default_factory=tuple)

    @property
    def publishable(self) -> bool:
        """False when this source's figures must be withheld rather than shown."""
        if self.severity == MISSING:
            return False
        return not (self.severity == EXPIRED and self.on_expired == "withhold")

    @property
    def marked(self) -> bool:
        """True when a figure fed by this source should carry a staleness badge."""
        return self.severity != FRESH

    def describe(self) -> str:
        age = f"{self.age_days}d" if self.age_days is not None else "age unknown"
        return f"{self.source_id}: {self.severity} ({self.published or 'no date'}, {age})"


def load_registry(path: Path | None = None) -> pd.DataFrame:
    df = pd.read_csv(path or REGISTRY, comment="#", dtype=str).fillna("")
    for c in ("cadence_days", "stale_days", "expired_days"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _iso(v) -> str:
    try:
        d = pd.to_datetime(v, errors="coerce")
        return "" if pd.isna(d) else d.date().isoformat()
    except Exception:  # noqa: BLE001
        return ""


def resolve_as_of(row: pd.Series, root: Path = ROOT) -> str:
    """Return the source's publication date as ISO, or "" when it cannot be established.

    Never raises: an unresolvable date is a fact about the source, not a crash.
    """
    method = str(row.get("as_of_method", "")).strip()
    art = str(row.get("artifact", "")).strip()
    path = root / art if art else None
    try:
        if method == "manual" or not method:
            return _iso(row.get("published", ""))
        if path is None or not path.exists():
            return _iso(row.get("published", ""))
        if method == "xlsx_run_date":
            return _iso(xlsx_run_date(path))
        if method == "zip_member_mtime":
            with zipfile.ZipFile(path) as z:
                newest = max((i.date_time for i in z.infolist()), default=None)
            return "" if newest is None else datetime(*newest).date().isoformat()
        if method.startswith("csv_max:"):
            col = method.split(":", 1)[1]
            df = pd.read_csv(path, comment="#", dtype=str)
            if col not in df.columns:
                return _iso(row.get("published", ""))
            vals = pd.to_datetime(df[col], errors="coerce").dropna()
            return "" if vals.empty else vals.max().date().isoformat()
    except Exception:  # noqa: BLE001
        return _iso(row.get("published", ""))
    return _iso(row.get("published", ""))


def _severity(row: pd.Series, published: str, exists: bool, today: date) -> tuple[str, int | None]:
    if str(row.get("artifact", "")).strip() and not exists:
        return MISSING, None
    if not published:
        # An undated source is never fresh. It is treated as stale so it is marked, not trusted.
        return UNDATED, None
    age = (today - date.fromisoformat(published)).days
    if str(row.get("cadence", "")).strip() == "archival":
        return FRESH, age
    exp, sta = row.get("expired_days"), row.get("stale_days")
    if pd.notna(exp) and age > exp:
        return EXPIRED, age
    if pd.notna(sta) and age > sta:
        return STALE, age
    return FRESH, age


def check(source_id: str, *, today: date | None = None, registry: pd.DataFrame | None = None,
          root: Path = ROOT) -> SourceStatus:
    reg = registry if registry is not None else load_registry()
    hit = reg[reg.source_id == source_id]
    if hit.empty:
        raise KeyError(f"{source_id} is not in the freshness registry")
    return _status(hit.iloc[0], today or date.today(), root)


def _status(row: pd.Series, today: date, root: Path) -> SourceStatus:
    art = str(row.get("artifact", "")).strip()
    exists = bool(art) and (root / art).exists()
    published = resolve_as_of(row, root)
    sev, age = _severity(row, published, exists, today)
    return SourceStatus(
        source_id=row.source_id, label=row.label, artifact=art, cadence=row.cadence,
        published=published, vintage=str(row.get("vintage", "")), age_days=age, severity=sev,
        on_expired=str(row.get("on_expired", "mark")) or "mark", note=str(row.get("note", "")),
        feeds=tuple(str(row.get("feeds", "")).split()))


def check_all(*, today: date | None = None, registry: pd.DataFrame | None = None,
              root: Path = ROOT) -> dict[str, SourceStatus]:
    reg = registry if registry is not None else load_registry()
    d = today or date.today()
    return {r.source_id: _status(r, d, root) for _, r in reg.iterrows()}


def gate(st: SourceStatus, log=print) -> bool:
    """Log at the right volume and return whether this source's figures may be published."""
    if st.severity == FRESH:
        return True
    msg = f"freshness: {st.describe()} — {st.label}"
    if st.severity in (EXPIRED, MISSING) and st.on_expired == "fail":
        raise SourceExpired(msg + " — this source cannot be missing or expired; refusing to publish")
    if not st.publishable:
        log(msg + f" — figures fed by this source are withheld ({' '.join(st.feeds)})")
    else:
        log(msg + " — published with a staleness mark")
    return st.publishable


def write_report(statuses: dict[str, SourceStatus], out: Path = OUT) -> pd.DataFrame:
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{
        "source_id": s.source_id, "label": s.label, "artifact": s.artifact, "cadence": s.cadence,
        "published": s.published, "vintage": s.vintage, "age_days": s.age_days,
        "severity": s.severity, "on_expired": s.on_expired, "publishable": s.publishable,
        "feeds": " ".join(s.feeds), "note": s.note,
    } for s in statuses.values()])
    df.to_csv(out / "source_freshness.csv", index=False)
    return df


def worst(statuses: dict[str, SourceStatus]) -> str:
    order = [FRESH, STALE, UNDATED, EXPIRED, MISSING]
    return max((s.severity for s in statuses.values()), key=order.index, default=FRESH)


def main() -> None:
    import argparse
    import sys
    ap = argparse.ArgumentParser(prog="caiso-siting freshness",
                                 description="Report each source's publication date against its own cadence.")
    ap.add_argument("--fail-on", choices=["never", "stale", "expired"], default="never")
    a = ap.parse_args()
    st = check_all()
    df = write_report(st)
    cols = ["source_id", "cadence", "published", "age_days", "severity", "publishable"]
    print(df[cols].to_string(index=False))
    print(f"\nworst: {worst(st)}  (thresholds are per-source; see data/source_freshness.csv)")
    # Only a source the registry marks on_expired=fail can fail the build. A never-fetched
    # optional source is MISSING and its figures are withheld — that is the system working, not a
    # reason to stop publishing everything else.
    bad = {"stale": (STALE, UNDATED, EXPIRED, MISSING), "expired": (EXPIRED, MISSING)}.get(a.fail_on, ())
    blocking = [s for s in st.values() if s.severity in bad and s.on_expired == "fail"]
    if blocking:
        for s in blocking:
            print(f"BLOCKING: {s.describe()} — {s.label}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
