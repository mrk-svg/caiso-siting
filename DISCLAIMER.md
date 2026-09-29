# Disclaimer

## This is a screening tool. It is not engineering advice.

`caiso-siting` reads public filings published by the California ISO, the U.S. Energy
Information Administration, PG&E and county GIS offices, and arranges what those files
already say into one page per interconnection node. It does not model a grid, run a power
flow, price a project, or predict an outcome. It tells you what has been filed and what has
happened to projects filed before you.

**No number on this site or in these outputs is a substitute for a study, a stamped design,
a deliverability assessment, an offtake analysis, or professional advice of any kind.**

## Before you act on anything here

Verify it against the source. Every output row carries `source_file`, `source_run_date`,
`pipeline_commit` and `pipeline_run` for exactly this reason: so you can open the filing the
number came from and read it yourself. If a figure here disagrees with the CAISO filing, the
filing is right and this tool is wrong — please open an issue so it stops being wrong.

## What this tool is known not to know

The methodology page carries the current list. In summary: CAISO's public files do not name
the customer behind a queue position, do not state a reason for withdrawal, and do not
publish study costs, network upgrade cost allocations, or curtailment history. Anything in
those categories is absent here, marked "Not public", and is never estimated, inferred or
filled in.

## No causal claims

Attrition, churn and survival figures on this site describe what happened to a population of
filings. They do not explain why, and they do not forecast. A node where many projects
withdrew is a node where many projects withdrew; the tool has no access to the reasons and
does not guess at them.

## No warranty

The code is provided under the MIT Licence, which disclaims warranties and limits liability in
respect of the software — read `LICENSE`. The outputs are provided under ODbL 1.0, whose section 8
disclaims warranties and limits liability in respect of the data — read `LICENSE-DATA.md`.

Independently of either licence: every figure, page, CSV and chart this project produces is offered
as a screening aid only, with no warranty of accuracy, completeness or fitness for any purpose, and
no liability is accepted for any decision taken in reliance on it. Known defects are published in
`KNOWN_ISSUES.md` and should be read before any figure is quoted. The upstream data carries its own
disclaimers: the California ISO publishes its materials "AS IS and without warranties of any kind,
either express or implied," and disclaims liability for any damages arising from their use. Nothing
here improves on that.

The author is an energy engineer, not a licensed Professional Engineer, and holds no
engineering licence in California or any other jurisdiction. Nothing in this repository is
offered as, or should be relied upon as, the work of a licensed professional. No engineering
services are offered or provided through this repository, and no professional or advisory
relationship is created by using it, opening an issue, or corresponding with the author about it.

## No investment or legal advice

Nothing here is investment, financial or legal advice, an offer, a solicitation, or a
recommendation to acquire, develop, finance or dispose of any project, site or security.

## Independence

This project is not affiliated with, endorsed by, sponsored by, or connected to the
California ISO, the U.S. Energy Information Administration, PG&E, Southern California
Edison, San Diego Gas & Electric, the California Energy Commission, the California Public
Utilities Commission, or any other agency or utility whose published data it reads. All
trademarks belong to their owners and are used only to identify the source of a file.
