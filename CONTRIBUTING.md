# Contributing

The most valuable thing you can send this project is **a number that is wrong**.

This tool encodes judgment calls about public filings — which substations sit inside a local
capacity area, which queue positions belong to the same point of interconnection, which
withdrawal dates count as censored. Those calls were made by reading PDFs. Some of them are
wrong, and the people who know which ones are people who work at those substations.

You do not need to write code to fix this project. You need to tell us what you know.

## Reporting a wrong number

Open an issue using the **Data correction** template. It asks for four things:

1. The page or output file, and the exact figure you are looking at.
2. What it should say.
3. The public source that shows it — a CAISO filing, a PTO notice, a tariff section, an EIA
   form. A document anyone can open.
4. How confident you are, and whether anything about the underlying facts is ambiguous.

Corrections are triaged on the source, not on the reporter. An issue with a filing cited gets
fixed; an issue that says "that's not right, trust me" gets a reply asking for the filing.
That is not scepticism about you — it is the rule that keeps every figure in this repository
traceable, and it applies to the maintainer too.

**What we cannot accept:** non-public information. If you know something because of your job
and it is not in a public filing, please do not put it in an issue. It cannot be used here,
and posting it may cause you a problem. The project's stated gaps stay gaps until a public
source closes them.

## Correcting the hand-built data files

Four files in `data/` were built by hand from published documents and are where most errors
live:

| File | What it encodes | Source it was read from |
|---|---|---|
| `lcr_areas.csv` | substation → local capacity area, in/out relation | CAISO Local Capacity Technical Report |
| `poi_overrides.csv` | corrected substation coordinates | operator knowledge, PTO maps |
| `poi_pnodes.csv` | POI → OASIS pricing node | CAISO OASIS node list, hand-confirmed |
| `poi_availability.csv` | POI availability statements | CAISO / PTO market notices |

Every row needs a `source` and `source_date`. A pull request that changes a row without
changing its source will be asked for one. Values may not contain `#` — pandas reads these
files with comment handling on, and a `#` truncates the field.

## Code contributions

Run before opening a PR:

    ruff check .
    python -m pytest -q

Both must be clean. New behaviour needs a test; the suite is the only thing standing between
this project and silently publishing a wrong number.

House rules, non-negotiable, because they are the product:

- **Every figure traces to a source row.** If you cannot name the file and column a number
  came from, it does not go on a page.
- **No composite scores.** No "grid-readiness index", no 0–100 rating, no weighted blend of
  unlike quantities. They hide their assumptions and cannot be checked.
- **No causal language.** The files do not carry reasons. Write what happened, never why.
- **No estimated, modelled or inferred dollar figures.** Ever.
- **Unknown is a first-class value.** If the data does not support a figure, the page says
  "Not public" or "Not here yet" and explains which. It does not fall back to zero, blank or
  a guess.
- **No names of private individuals.** Parcel owner names are never read. Owners in EIA-860
  that classify as people rather than organisations are counted, never named.
- **Small-n figures are dimmed, not hidden or rounded away.** See `MIN_N` and
  `MIN_DENOM_MW` in `site.py`.

## Security

Do not open a public issue for a security problem. `SECURITY.md` has the reporting route.

## Licensing of what you contribute

Code contributions are licensed under the MIT Licence, matching the repository. Contributions
to the hand-built data files are contributed under ODbL 1.0, matching the derived database
those files feed — see `LICENSE-DATA.md`. By opening a pull request you confirm you have the
right to contribute the material and that it is not confidential to an employer or client.
