# Security notes

This project downloads spreadsheets from CAISO and PG&E, renders their contents into a public static site,
and runs unattended on GitHub Actions. That is three attack surfaces; here is what each one is and what guards it.

## 1. Files we download and parse

Public `.xlsx` from caiso.com and pge.com (plus a CSV from Overpass and JSON from ArcGIS REST). Parsed with
`openpyxl` via pandas — **no macro execution path exists**: openpyxl does not run VBA, and the files are `.xlsx`
(no `vbaProject.bin`), confirmed by inspecting every archive. `wdat_pge.xlsx` carries Excel *external workbook
links*; pandas ignores them, but if you open that file in Excel yourself, decline "update links".
Zip-bomb exposure is bounded: the largest file inflates 8×; pandas reads sheets, not arbitrary members.
OASIS zips are opened in memory with `zipfile`; a non-zip or XML error body raises rather than being executed.
All downloads use HTTPS (OASIS included, as of 1.3.2). Nothing downloaded is ever executed.

## 2. What we publish

`site/` is generated from those files. Every value that comes from a source file passes through
`html.escape` before it lands in HTML (`site.py:esc`), and the map (`nodes_map.html`) escapes values in the
browser before inserting them into popups and serialises its data with `</` neutralised so a hostile string
cannot break out of the `<script>` block. Leaflet is loaded from a CDN **with subresource-integrity hashes**, so a
tampered CDN file will not run. Output CSVs are checked in tests for cells that Excel would treat as formulas
(`=`, `+`, `-`, `@` prefixes); none exist today. No owner names, no credentials, no secrets anywhere in the tree.

## 3. How it runs unattended

`weekly.yml` uses only first-party `actions/*` steps and the repository `GITHUB_TOKEN`; no third-party actions,
no secrets. Permissions are declared explicitly (`contents`, `pages`, `id-token`, `issues`). The diff issue body
is passed to `github-script` as data, not interpolated into a shell. Dependabot watches both pip and the
actions themselves. To harden further, pin each `uses:` to a commit SHA rather than a tag.

## Known residual risks

- The pipeline trusts the *content* of CAISO/PG&E files as data. A malformed file breaks a parse loudly
  (header-drift guard) rather than silently; it cannot execute anything.
- `caiso-siting layers`/`parcels`/`oasis` make live requests to public GIS/market APIs from your machine —
  read-only GETs, no credentials, but they do reveal your IP and the substations you are looking at to those
  servers.
- `data/documents_seen.csv` and `outputs/new_documents.md` contain URLs scraped from watched pages; treat
  links there as untrusted until you have opened the source page yourself.

Report a problem by opening an issue titled `security:`.
