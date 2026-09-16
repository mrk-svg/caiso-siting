# Licensing of the data in this repository

The `LICENSE` file covers **the code**. It does not, and cannot, cover the data — because the
data is not ours to license. This file says what covers what.

## Short version

| What | Licence |
|---|---|
| Everything under `src/`, `tests/`, and the build scripts | MIT (see `LICENSE`) |
| `data/lcr_areas.csv`, `poi_overrides.csv`, `poi_pnodes.csv`, `poi_availability.csv` | ODbL 1.0 |
| `outputs/nodes.csv` and `outputs/poi_geocode.csv` (OSM-derived) | ODbL 1.0 |
| The rendered pages and map under `site/` | ODbL Produced Works — attribution |
| Every other file under `outputs/` | not ours to license — publishers' own terms |
| Upstream files fetched by the pipeline | each publisher's own terms — see `DATA_LICENSES.md` |

## Why some outputs are ODbL and not MIT

Substation coordinates in this project come from OpenStreetMap via Overpass, which is licensed under
the Open Database Licence 1.0. ODbL is share-alike **for databases**: a database built using OSM data
and distributed publicly is a Derivative Database and must be offered under ODbL. Two files carry
OSM-derived content — `outputs/nodes.csv` and `outputs/poi_geocode.csv`, which hold `lat`, `lon`,
`osm_name` and `geo_method` for the nodes whose positions were resolved from OSM. Both are therefore
offered under ODbL 1.0. Publishing them under MIT would be a licence violation, and quietly dropping
the coordinates to avoid the obligation would make the outputs less useful and less checkable.

The rendered pages and map under `site/` are Produced Works under ODbL, which require attribution
rather than share-alike. They are distributed with that attribution, on the map itself and in the
footer of every page.

**The remaining files under `outputs/` contain no OSM-derived content.** They are derived from CAISO
reports, PG&E's WDAT file and EIA-860 — material this project does not own and does not purport to
license. They are redistributed on their publishers' own terms, recorded in `DATA_LICENSES.md`, and
carry the attribution in `outputs/ATTRIBUTION.txt`. EIA-860 in particular is a U.S. federal
government work in the public domain; offering it under a share-alike licence would assert a
restriction that does not exist and that this project has no standing to impose. To the extent any
original selection and arrangement in those files is this project's own, it is offered under ODbL 1.0
for consistency.

Full licence text: https://opendatacommons.org/licenses/odbl/1-0/

## If you reuse the outputs

Attribution required on every map, page or derived dataset:

    Substation positions © OpenStreetMap contributors, ODbL.
    Queue, deliverability and local capacity data: California ISO.
    Generator and storage data: U.S. Energy Information Administration, Form EIA-860.

If you build a database from `outputs/`, publish it under ODbL too.

## California ISO material

The California ISO's published terms permit the use of materials that were compiled from
information available for public use, **provided you keep all copyright, trademark and other
proprietary notices intact and credit the California ISO**. This project therefore credits
CAISO in the footer of every generated page, in `DATA_LICENSES.md`, and in the `source_file`
column of every output row.

Two limits follow from those terms and are enforced in the pipeline:

1. **OASIS API data is never committed.** CAISO's terms treat the CAISO API and CAISO Data as
   proprietary, with a narrower licence than the website's published reports. Raw OASIS
   responses are cached locally, are gitignored, and only derived aggregates are published.
2. **CAISO is credited, never implied as a source of endorsement.** This project is not
   affiliated with the California ISO. See `DISCLAIMER.md`.

## Sources of ambiguity

The maintainer is not a lawyer and this file is not legal advice. Two areas are read
conservatively rather than aggressively:

- **Redistributed CAISO spreadsheets.** `data/tpd_2024.xlsx` and `data/tpd_2025.xlsx` are
  published CAISO allocation-results workbooks kept in the repository so that the pipeline is
  reproducible without a live fetch. They are redistributed with credit, unmodified, under the
  terms above. If CAISO asks for them to be removed, they will be removed the same day and the
  pipeline will fetch them instead; nothing in the code depends on them being local.
- **County GIS layers.** Parcel and zoning layers are read live and never redistributed.
  Owner names are never read into memory. This project does not read or publish parcel owner names. That is its own policy, not a statutory requirement: California assessor records are generally public. See `DATA_LICENSES.md`.

## Takedown

If you publish data this project reads and you believe it is redistributed here beyond your
terms, open an issue titled `licensing:` or contact the maintainer through the repository. The
default response is to remove the material first and discuss afterwards.
