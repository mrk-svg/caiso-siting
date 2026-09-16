# Security notes

This project downloads spreadsheets from CAISO and PG&E, renders their contents into a public static site,
and runs unattended on GitHub Actions. That is three attack surfaces; here is what each one is and what guards it.

## 1. Files we download and parse

Public `.xlsx` from caiso.com and pge.com (plus a CSV from Overpass and JSON from ArcGIS REST). Parsed with
`openpyxl` via pandas — **no macro execution path exists**: openpyxl does not run VBA, and the files are `.xlsx`
(no `vbaProject.bin`), confirmed by inspecting every archive. `wdat_pge.xlsx` carries Excel *external workbook
links*; pandas ignores them, but if you open that file in Excel yourself, decline "update links".
Zip-bomb exposure on the EIA path is bounded by an enforced control: `eia860.verify()` caps each member's
uncompressed size and the compression ratio. The xlsx path has no such per-member control yet — downloads are
capped at 80 MB by `fetch.get_bytes`, which bounds the input but not the inflation. A hostile workbook could
still cost memory in `pd.read_excel`; it cannot execute anything. Tracked in KNOWN_ISSUES.md.
OASIS zips are opened in memory with `zipfile`; a non-zip or XML error body raises rather than being executed.
All downloads go through `fetch.get_bytes`, which refuses a non-HTTPS URL, refuses any redirect that
downgrades to plaintext or leaves a hardcoded host allow-list, and caps the body — `requests` otherwise follows
up to 30 redirects with no downgrade protection, so pinning the first URL guaranteed nothing about the last.
Every download writes a `.part`, verifies it, and only then replaces the real file, so a 200 carrying an HTML
error page cannot destroy a good local copy. Nothing downloaded is ever executed.

## 2. What we publish

`site/` is generated from those files. Every value that comes from a source file passes through `html.escape` before it lands in HTML
(`site.py:esc`), including the caller-supplied strings in the survival SVG that the page inlines raw, and the map (`nodes_map.html`) escapes values in the
browser before inserting them into popups and serialises its data with `</` neutralised so a hostile string
cannot break out of the `<script>` block. Leaflet is **vendored into the repository** (`src/caiso_siting/vendor/`,
BSD-2, hashes verified against the upstream SRI digests at the time of vendoring) and copied into `site/` at build
time, so the published site loads no third-party script at all: no CDN to be tampered with, and no request from a
reader's browser to anyone but GitHub Pages and the map tile server. Output CSVs are escaped on write: `config.csv_safe` prefixes any string cell beginning `=`, `+`, `@`, tab or
carriage return — and `-` followed by a non-digit — with a single quote, so a hostile CAISO or PG&E cell cannot
become a live formula in a reader's spreadsheet. Numeric cells are untouched; a negative longitude is not a
formula. Asserted in `tests/test_csv_safety.py`. No owner names, no credentials, no secrets anywhere in the tree.

## 3. How it runs unattended

`weekly.yml` uses only first-party `actions/*` steps and the repository `GITHUB_TOKEN`; no third-party actions,
no secrets. Permissions are declared **per job**, not at workflow level: `build` holds `contents`, `pages` and `issues`;
`deploy` holds only `pages` and `id-token`, so the action that publishes the site cannot rewrite the repository.
CI itself runs with `contents: read` only. Every `uses:` is **pinned to a commit SHA**, not a tag, so a compromised or re-pointed tag in
an upstream action cannot execute inside a job that holds a write token; the human-readable version follows in a
trailing comment and Dependabot still proposes bumps. There is no `pull_request_target` or `workflow_run` trigger
anywhere in this repository — those are the usual route by which a fork's pull request gets hold of a write token,
and adding one should be treated as a security change, not a convenience. The diff issue body is passed to
`github-script` as data, not interpolated into a shell. Dependabot watches both pip and the actions, and `ci.yml`
runs `pip-audit --strict` on every push so a new advisory fails the build rather than waiting for a Dependabot PR.

## Known residual risks

- The pipeline trusts the *content* of CAISO/PG&E files as data. A malformed file breaks a parse loudly
  (header-drift guard) rather than silently; it cannot execute anything.
- `caiso-siting layers`/`parcels`/`oasis` make live requests to public GIS/market APIs from your machine —
  read-only GETs, no credentials, but they do reveal your IP and the substations you are looking at to those
  servers.
- `data/documents_seen.csv` and `outputs/new_documents.md` contain URLs scraped from watched pages; treat
  links there as untrusted until you have opened the source page yourself.

## Reporting

Report privately through GitHub's security advisory form:
<https://github.com/mrk-svg/caiso-siting/security/advisories/new>

Please do not open a public issue for a security problem. There is no bounty and no SLA — this is a
one-person project — but reports are read and acknowledged, and the repository has no users to put at
risk by fixing something slowly and openly.
