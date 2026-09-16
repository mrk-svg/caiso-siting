# What I actually learned building caiso-siting

An inventory, domain by domain, of everything this project taught — and an honest rating on each
one, because a thing you can name is not the same as a thing you can defend.

## How to read the ratings

**DEFENSIBLE** — You made the decision yourself, you know why the alternative was worse, and you
can survive three follow-up questions. Claim it in an interview.

**WORKING** — You did it and could do it again, but you would look things up and you have only
seen one case. Say "I've done this once" and describe the case. Do not generalise.

**EXPOSED** — It happened in front of you. You know the word and roughly what it means. Do not
claim it; if it comes up, say "I ran into that but I wouldn't call myself fluent."

The ratings are the most useful part of this document. Getting caught overclaiming costs more
than the claim was worth.

---

# 1. Energy market and interconnection

This is the deepest learning in the project and the reason it exists. Everything else is
transferable skill; this is domain knowledge that took reading the actual filings.

### The queue is a process with gates, not a list — DEFENSIBLE

An interconnection request is not a project waiting in line. It passes through cluster intake,
Phase I and Phase II studies, an interconnection agreement, and commercial operation, and the
population shrinks at each gate. Before this project you would have described "the queue" as a
backlog. Now you can describe it as a funnel with measurable survival between stages, which is
why the node page counts `p2_reached` separately from raw queue count. **The insight to keep:
counting what is queued at a node tells you almost nothing; counting what survived each gate
tells you almost everything.**

### Requested deliverability ≠ allocated deliverability — DEFENSIBLE

Cluster 15 projects state a deliverability request. That is an ask, not a grant. Full Capacity
Deliverability Status is awarded through the Transmission Plan Deliverability allocation process,
which runs on its own cycle, in its own workbook, with its own rules. Conflating the two is the
single most common error in amateur queue analysis, and your README says so out loud. This is the
distinction that makes an interconnection engineer decide you are worth talking to.

### TPD allocation groups A–D — DEFENSIBLE

From the 2025 TPD Allocation Report: group A is an executed PPA or LSE own-load, group B is
shortlisted or in PPA negotiation, group C is already in commercial operation, group D is no PPA
at all under section 8.9.2.3. The consequence you worked out yourself: a refusal only means
something once you know which group it hit. Refusing group D is the tariff working as designed.
Refusing group A is a signal about the transmission system. **This is your strongest single piece
of domain evidence** — it is a distinction the data does not hand you, that you had to go to the
allocation report to find, and that changes the meaning of a number you already had.

### Local capacity areas and the Resource Adequacy geography — DEFENSIBLE

The Local Capacity Technical Report defines areas and sub-areas by listing delineating
substations. A resource inside a local capacity area can earn local RA value; one outside cannot,
regardless of how good the interconnection is. You learned that the relation is not a simple
lookup: a substation can be named as a boundary and still sit outside, the same name can exist on
two utilities' systems, and a queue POI can sit on the low side of a boundary substation and
therefore be inside when the name suggests otherwise. That last one is exactly the error you made
at Antelope, Mercy Springs and Bellota and then fixed. **The general lesson: a boundary list is
not a membership list, and reading it as one produces confidently wrong answers.**

### Queue reform changed the population, not just the rules — DEFENSIBLE

Cluster 14 ran under the FERC-approved September 2021 special procedures with roughly 373 requests
and around 150 GW. Cluster 15 ran under intake scoring that cut 541 requests to 255, then to 177,
then to about 145. Those two cohorts are not comparable populations, which is why your survival
curves carry a regime annotation. **This is the thing most people miss:** a process change makes a
time series discontinuous, and plotting across the discontinuity invents a trend.

### Withdrawal is a portfolio decision more often than a grid verdict — DEFENSIBLE

CAISO's files carry no withdrawal reason beyond "IC Request". A developer may withdraw because
network upgrade costs came in high, because an offtake fell through, because they were never
serious, or because they refiled at a better POI. You cannot tell which, so the tool says what
happened and refuses to say why. **Knowing that a data set cannot support a causal claim, and
then not making the claim, is a professional instinct, not a technical one.**

### Storage churn as distinct from general attrition — WORKING

You separated storage withdrawals from the 2008-era wind and solar that also withdrew, because a
node full of abandoned decade-old solar requests is a different story from a node where storage
keeps arriving and leaving. Good instinct, one implementation, no external validation yet.

### What is already built vs what is queued — WORKING

EIA-860 gives operating and proposed generators, storage capacity in MWh, and a reported LMP node
designation per plant. Joining it to queue nodes answers "who is already here" alongside "who is
coming". You learned the shape of the form — Plant, Generator (Operable and Proposed), Energy
Storage, Owner, as separate sheets keyed on Plant Code — and that the balancing authority field
is how you scope to CAISO.

### Nodal price and the storage revenue question — EXPOSED

You know that day-ahead LMP at a pricing node drives storage arbitrage value, that a TB4 spread is
a first-pass proxy, and that OASIS publishes the data behind a rate limit. You have not built the
layer at scale — only about 33 nodes have a confirmed PNode. **Do not claim you can value a
storage project.** Say you scoped the layer and know why it is hard: the POI-to-PNode mapping is
not published in a usable form and has to be hand-confirmed.

### WDAT and the distribution-level queue — WORKING

PG&E's Wholesale Distribution Access Tariff queue is a different queue at the same substations,
and it is not CAISO deliverability. You know it exists and that conflating it is an error.

### Tax credit timing — WORKING

Wind and solar credits end for projects placed in service after 2027-12-31 unless construction
began by 2026-07-04; storage keeps the full credit through 2033, then 75% in 2034 and 50% in 2035;
foreign-entity-of-concern rules bite from 2026. You verified these rather than trusting a summary,
and you correctly refused to build an "ITC cliff trigger" feature on top of them, because
begin-construction status is not public and the feature would have required inventing it.

---

# 2. Regulatory literacy — the meta-skill

Separate from any single fact, the project taught a habit that transfers to every energy job.

### Reading the primary document instead of the summary — DEFENSIBLE

Every domain fact above came from a filing: the allocation report, the Local Capacity Technical
Report, the tariff section, the EIA form. Not from an article about them. **In an interview, the
way to demonstrate this is to describe a case where the summary would have misled you** — the TPD
groups are that case, because no summary of "deliverability was denied" contains the distinction
that makes the denial meaningful.

### Public files are messy in ways that reveal how they are produced — DEFENSIBLE

CAISO's county column contains "king", "San Bernadino", "Kings and Fresno". That is not a data
quality problem to be silently cleaned; it tells you the field is typed by humans at intake and
therefore cannot be used as a key. Learning to read the mess as evidence about the process —
rather than as noise to be scrubbed — is genuinely senior behaviour.

### Knowing what is structurally unpublished — DEFENSIBLE

Customer identity behind a queue position, study costs, network upgrade cost allocation,
withdrawal reasons, financial security postings, begin-construction status, landowner intent,
load-side interconnection. None of it is public, none of it is inferable, and your methodology
page lists all of it. **Being able to say "that's not knowable from public data, and here's where
it does live" is a more impressive answer than any number you could produce.**

---

# 3. Git and GitHub as a platform

You arrived knowing git as "save my work". You leave knowing GitHub as an execution environment
with a permission model.

### Git mechanics — WORKING, and enough

- `git commit -am` stages modified tracked files only; untracked files need `git add -A`. You lost
  a whole `notes/` directory to this once.
- Git derives author identity from `user.name`/`user.email` and silently falls back to a
  hostname-derived address when they are unset, which is how commits ended up authored by your
  machine. Fixed with `git config` and `git commit --amend --reset-author`.
- `.git/index.lock` is a mutex, not corruption. A crashed or killed git leaves it behind and every
  later command refuses until it is removed.
- The difference between a working tree, the index and a commit — you now feel this rather than
  reciting it, because you have been caught out by each layer.

### GitHub Actions — DEFENSIBLE for a solo project

This is the biggest software skill gained, and it is genuinely marketable.

- A workflow is a YAML file in `.github/workflows/`, triggered by events (`push`, `pull_request`,
  `schedule`), running jobs on ephemeral runners.
- `permissions:` at the top declares what the automatic `GITHUB_TOKEN` can do. Your CI runs with
  `contents: read`; the weekly job needs `contents: write`, `pages: write`, `id-token: write`
  because it commits data and deploys the site. **Least privilege per workflow, not per repo.**
- A scheduled workflow must decide whether anything actually changed. Yours gates the commit and
  the issue on a new CAISO snapshot directory, because automation that fires unconditionally
  trains you to ignore it.
- `actions/github-script` runs JavaScript against the GitHub API — you used it to open the weekly
  diff issue, passing the body as data rather than interpolating it into a shell command, which is
  the difference between a script and an injection.
- A newly added workflow file is not registered until it lands on the default branch, which is why
  the first weekly run needed a touch commit.
- GitHub Pages serves from an artifact built by `upload-pages-artifact` and published by
  `deploy-pages`, and **Pages on a free account requires a public repository** — which is why your
  site went dark the moment you made the repo private.

### Dependency and supply-chain management — DEFENSIBLE

- Dependabot opens PRs for both pip dependencies and the actions themselves; you merged five and
  learned that action major-version bumps sometimes carry runtime changes (the setup-python Node
  20 deprecation).
- `uses: actions/checkout@v7` trusts a *mutable tag*. Pinning to a commit SHA with the version in a
  trailing comment removes that trust while keeping Dependabot able to propose bumps. You now know
  why this matters specifically: a compromised tag executes inside a job that holds a write token.
- `pull_request_target` and `workflow_run` are the triggers that hand a fork's code a token with
  write access. Your repo has neither, and you now know to treat adding one as a security decision.
- A `pip-audit --strict` step fails the build on a known advisory, which is faster than waiting for
  a Dependabot PR. You also learned to set version floors directly (`urllib3>=2.7.0`,
  `idna>=3.15`) with the advisory ID in a comment, so the next reader knows why the floor exists.

### Repository hygiene as a signal — DEFENSIBLE

CI badge, changelog with reasons rather than a list of commits, issue templates that ask for what
you actually need, a security policy with a private reporting route, a citation file, a
contributing guide that states the house rules. **None of this is code, and all of it is read by
anyone evaluating whether the repo is serious.**

### `gh` CLI and authentication — WORKING

Device-code flow, scopes, `gh repo edit --visibility`. You learned the hard way that pasting
commands into an interactive prompt sends them to the prompt, not the shell.

---

# 4. Software engineering discipline

The part that transfers to any data job regardless of industry.

### Provenance as a design requirement — DEFENSIBLE

Every output row carries `source_file`, `source_run_date`, `pipeline_commit`, `pipeline_run`. This
was a decision, not a convenience: it means any figure on any page can be traced back to a file and
a version of the code. Almost no one does this, and it is the single design choice that makes the
project's central claim — every number traceable — actually true rather than aspirational.

### Unknown is a type, not a blank — DEFENSIBLE

Four distinct states where most tools have one: **dimmed** (too few projects to quote reliably),
**undefined** (the denominator does not exist), **not public** (the filings do not contain it), and
**not here yet** (we have not built the layer). Collapsing these to a blank cell or a zero is the
most common lie in data products, and refusing to collapse them is your strongest software
argument.

### Failing loudly beats failing quietly — DEFENSIBLE

The header-drift guard breaks a parse rather than producing wrong columns. A corrupt EIA zip yields
empty columns plus a warning rather than killing the whole build. **The general principle you can
now state: for a data pipeline, a crash is a good outcome and a plausible wrong number is the worst
one.**

### Tests prove the code matches your assumptions, not that your assumptions are right — DEFENSIBLE

You had 337 passing tests while the EIA join was attributing plants to the wrong substations,
because line-midpoint nodes were eligible as nearest neighbours and distance ties resolved by
DataFrame row order. Nothing in the suite could catch it, because the suite encoded the same
assumption as the bug. **This realisation is worth more than the test count.** It is what turned
the project towards adversarial review and towards asking strangers for wrong numbers.

### Adversarial review as a routine, not an event — DEFENSIBLE

Running reviewers whose job is to find your errors, ranking findings by severity, fixing the real
ones, and explicitly documenting the ones you decided not to fix with the reason. That last part —
a written decision to *not* fix something — is what separates a maintained project from an
abandoned one.

### Determinism and idempotence — WORKING

The same inputs produce the same outputs; a rerun on unchanged data changes nothing. You found
this the hard way when a test pinned a live run date and broke on the next CAISO posting, and when
`join_tpd` wrote into `outputs/` during tests and polluted real files. **Tests must not write to
production output paths** is a lesson people usually learn on a team.

### Small-n honesty — DEFENSIBLE

`MIN_N` and `MIN_DENOM_MW` dim a ratio computed from too few projects instead of displaying it at
full confidence. A percentage from three projects and a percentage from three hundred look
identical on a page unless you make them look different.

### Python and data tooling — WORKING

pandas joins and the fact that a `merge` silently duplicates rows on a non-unique key; dedup as a
deliberate act (`drop_duplicates` on node, queue id and status, after you learned you had been
counting rows instead of projects); `openpyxl` for xlsx and why it cannot execute a macro;
`zipfile` for in-memory archives; vectorised haversine distance; `html.escape`; `string.Template`;
`ruff`; `pytest` fixtures and synthetic archive construction for tests.

### Python environments — WORKING

PEP 668 marks a Homebrew or system Python as externally managed and refuses `pip install`, which is
a feature: it protects the interpreter your OS depends on. The answer is a virtualenv, and
`pip install -e .[dev]` installs your own package in editable mode with its dev extras. You also
learned a venv is platform-specific — the binaries in it are Mach-O and cannot run on Linux.

### Shell reality — WORKING

Interactive zsh does not treat `#` as a comment by default, so pasting an annotated multi-line
block executes the annotations. Paste one command at a time, or put it in a script.

---

# 5. Security

### Threat modelling by surface — DEFENSIBLE

You can now name three surfaces and what guards each: files you download and parse, content you
publish, and code that runs unattended with a token. That framing — enumerate the surfaces, then
state the guard for each — is exactly how a security review is structured.

### Untrusted input handling — DEFENSIBLE

Escape at the boundary, every time, not selectively. You had `fact()` rendering a value unescaped
and a markdown link renderer that allowed attribute injection through a crafted URL, and both were
found by review rather than by intuition. **The lesson: "this field comes from a CAISO file so it's
safe" is the reasoning that produces every XSS bug ever shipped.**

### Verifying a download before trusting it — DEFENSIBLE

Write to a `.part` file, check the archive opens, check the member names against a regex, reject
executable suffixes, cap the uncompressed size and the compression ratio, *then* replace the real
file. You now know what a zip bomb is and what bounds it.

### Removing third parties from the serving path — DEFENSIBLE

Subresource integrity means a CDN script that has been tampered with will not execute — but SRI
does not help if the CDN is blocked or gone. Vendoring Leaflet into the repository, with its BSD-2
licence file and hashes verified against the upstream digests, removed the dependency entirely.
The published site now loads no third-party script at all.

### Spreadsheet formula injection — WORKING

A CSV cell beginning `=`, `+`, `-` or `@` is executed as a formula when opened in Excel. Your tests
assert no output cell does that. Most people have never heard of this.

### Least privilege and blast radius — DEFENSIBLE

You can now reason about what an attacker would actually get: your repo holds no secrets beyond the
automatic token, so a compromised action could rewrite your repository and nothing else. **Being
able to state the blast radius rather than saying "it's secure" is the professional version of this
answer.**

---

# 6. Law, licensing and copyright

This is the area where you went from zero to genuinely informed, and it is unusual for an engineer.

### Open source licences do different jobs — DEFENSIBLE

**MIT** is permissive: do anything, keep the notice, no warranty, no liability. **BSD-2** (Leaflet)
is effectively the same. **ODbL 1.0** (OpenStreetMap) is a *database* licence and it is
share-alike. These are not interchangeable and picking one is a design decision with consequences.

### The insight that almost caught you out — DEFENSIBLE

**A licence on your code does not license your outputs.** Substation positions come from
OpenStreetMap under ODbL. `outputs/nodes.csv` carries `lat`, `lon`, `osm_name`, `geo_method` — which
makes it a *Derivative Database*, not merely a *Produced Work*, and ODbL's share-alike obligation
attaches to derivative databases. Publishing those outputs under MIT would have been a licence
violation from the first day the repo went public. The fix was to license the outputs under ODbL
rather than to strip the coordinates.

**The general principle, which transfers everywhere:** when your product is built from other
people's data, ask separately what licenses the code, what licenses the input, and what licenses
the output. Most engineers only ever answer the first.

### Produced Work vs Derivative Database — DEFENSIBLE

A rendered map image made from OSM data is a Produced Work and needs attribution. A CSV of
coordinates extracted from OSM is a derivative database and needs attribution *and* share-alike.
The distinction turns on whether you are distributing the data or a picture of it.

### Terms of use are a contract you can actually read — DEFENSIBLE

You stopped assuming "it's a public report so it's free" and read CAISO's published terms. They
permit use of material compiled from publicly available information **provided you keep all
copyright and proprietary notices intact and credit the California ISO**, and everything is
supplied "AS IS" with liability disclaimed. Critically, the **API is carved out separately** —
CAISO asserts ownership of the CAISO API and CAISO Data with a narrower licence than the website's
published reports. So redistributing a published workbook with credit is fine; committing raw OASIS
API responses is not. **"Public" and "freely redistributable" are different words.**

### Documentation that contradicts practice is worse than none — DEFENSIBLE

Your `DATA_LICENSES.md` stated that raw downloads are never committed while two CAISO workbooks sat
tracked in the repo. Nobody had lied; the rule was written before the exception. But a reader who
finds one false statement in your documentation stops trusting all of it. **Rules must describe
what the repository actually does, and exceptions must be written down as exceptions.**

### Personal data and why you never read it — DEFENSIBLE

County parcel layers carry owner names. You never read them into memory at all — not read and
discarded, *never read* — and the project cites a California Government Code exemption as the
reason. (Verify the exact section before quoting it in public; the principle stands regardless of
the citation.) In EIA-860, owners that classify as individuals are counted but never named, via a
classifier that decides whether a string is an organisation or a person. It over-blocks — some
corporate names read as people — and you kept it that way, because **when a privacy classifier must
be wrong, it should be wrong in the direction of not naming someone.**

### Liability, disclaimers and the limits of a licence — DEFENSIBLE

MIT's warranty disclaimer covers the code. It does not cover the numbers the code emits. That gap
is why the project now carries a *reliance* disclaimer distinct from its *methodological* one: not
engineering advice, built by someone who is not a licensed PE, verify against the source filing, no
warranty, no affiliation — rendered on every page through the template path so a refactor cannot
silently drop it, with tests asserting it survives.

**The deeper point, which matters more than the text:** your real exposure was never a hacker. It
was someone relying on a wrong number in a decision worth millions while you hold no PE, no E&O
cover and no contract with them. The mitigation is a boundary stated in the product, not a
paragraph in a footer.

### Trademark and the appearance of endorsement — WORKING

Using "CAISO" to identify the source of a file is nominative use and fine. Building something that
looks like a CAISO product is not. Hence the explicit non-affiliation statement.

### Takedown posture — WORKING

The stated policy is to remove first and discuss afterwards, and the pipeline is built so nothing
depends on the redistributed workbooks being local. **Designing so that a takedown costs you
nothing is the engineering answer to a legal risk.**

---

# 7. Statistics and quantitative method

### Survival analysis and censoring — WORKING, tending DEFENSIBLE

Kaplan–Meier estimates the probability of surviving past time *t* with right-censored data —
projects still active have not failed, they just have not failed *yet*, and dropping them biases
the curve. You learned that the censor date is a decision, not a given: using the report posting
date could have placed a censor before a withdrawal that the same file recorded, quietly
understating attrition. It is now computed as the later of the posting date and the latest
withdrawal in the file. **Censoring is where survival analysis goes wrong, and knowing that is the
signal.**

### Cohorts must be comparable — DEFENSIBLE

Covered above under regime annotation, but it is a statistical lesson as much as a domain one: a
rule change between cohorts is a confound, and plotting across it manufactures a trend.

### Why you refused composite scores — DEFENSIBLE

A weighted blend of unlike quantities hides its weights, cannot be checked against a source, and
cannot be argued with. Every commercial tool in this space sells the score; a free tool that sold
one would be worse than useless because its errors would be invisible. **Be able to say this in one
sentence: you can argue with a number that traces to a filing, and you cannot argue with a 73.**

### Denominators and the difference between a rate and a count — DEFENSIBLE

`MIN_DENOM_MW`, the undefined-versus-dim distinction, counting distinct projects rather than rows.
Three separate bugs in this project came from denominator carelessness.

---

# 8. Geospatial

### Coordinates are not a given — DEFENSIBLE

No public CAISO file contains substation coordinates. Positions come from OpenStreetMap via
Overpass, from California Energy Commission transmission line geometry, and from hand overrides —
and each is tagged with `geo_method` recording how it was derived. **Recording provenance per row
is what made the EIA bug findable**, because you could ask "which of these positions are real
enough to join on" and get an answer.

### Approximate positions must be marked and then respected — DEFENSIBLE

A node positioned at the midpoint of a transmission line is not at that location. Once you had
`APPROX_METHODS`, the fix to the join was one line: only nodes with real positions
(`exact`, `override`, `cec-line`) are eligible as nearest neighbours.

### Joining by distance is a decision with a threshold — WORKING

A 5 km radius, nearest match wins, ties broken deterministically rather than by row order. You
learned that a spatial join is a modelling choice with a defensible parameter, not a lookup.

### Name collisions across utilities — DEFENSIBLE

MESA in SCE and MESA in PG&E are different substations. Any join on substation name must be
utility-aware or it silently merges unrelated facilities. This is the geospatial version of the
general lesson that human-typed strings are not keys.

---

# 9. Working with AI to build real software

Do not skip this one. It is the skill with the shortest half-life and the highest current demand,
and you now have a real, non-toy case study.

### Specification is the work — DEFENSIBLE

The AI wrote most of the Python. It did not know that TPD groups change the meaning of a refusal,
that C14 and C15 are not comparable, or that a line-midpoint node should not win a distance join.
Every one of those was a judgment you supplied. **The honest framing: the model is a fast
implementer with no stake in being right, and your value is in the specification and the review.**

### AI-generated code produces a specific failure mode — DEFENSIBLE

Not crashes. Plausible wrong answers with passing tests, because the tests were generated from the
same assumptions as the code. Your defence is adversarial review by a *separate* pass whose only
job is to find errors, plus tests written against the domain rather than against the implementation.

### Rejecting the pitch is part of the job — DEFENSIBLE

You were pitched congestion scores, readiness checklists, deliverability deserts, sunk-cost layers,
ITC cliff triggers, an NREL reV integration. You audited each against what public data can actually
support and rejected the ones that required inventing numbers, keeping only the deterministic ones.
**In an interview this is the story to tell about AI**, because it demonstrates the thing employers
are actually worried about: that you will ship whatever the model produced.

### Provenance discipline is what makes AI-assisted work auditable — DEFENSIBLE

Because every figure names its source file, a reviewer can check the output without reading the
code that produced it. That is how you make machine-written code trustworthy at scale, and it is a
genuinely forward-looking answer.

---

# 10. Product judgment

### Distribution is a separate problem from building, and harder — DEFENSIBLE

Fifteen thousand lines, 339 tests, weekly automation, zero users. You know now that a finished tool
and a used tool are different achievements, and that continuing to add features is the comfortable
way of avoiding the uncomfortable one.

### The right first metric is not usage — DEFENSIBLE

Not stars, not opens, not signups: **how many domain experts reply with a specific claim that a
number is wrong.** A tool nobody can correct is a tool nobody has checked.

### Open source is auditability, not distribution — DEFENSIBLE

For a trust-based data product, publishing the source *is* the credibility argument: a closed tool
asks to be trusted, an open one offers to be checked. But publishing changes nothing about whether
anyone finds it. Those are two separate problems and only one of them is solved by a git push.

### Where the actual scarcity is — DEFENSIBLE

The pipeline is reproducible by any competent engineer in a few weeks. The hand-built files are
not: 118 LCR rows read out of a PDF with in/out relations and utility disambiguation, plus the POI
overrides and the hand-confirmed pricing nodes. **The curation is the asset, the code is not**, and
you decided to give the curation away because credibility is worth more to you right now than
exclusivity. That is a strategy decision with a stated reason, which is what makes it defensible.

---

# 11. What you did not learn — say this out loud when asked

Being precise about the edges is what makes the rest credible.

- **You did not learn power systems analysis.** No load flow, no short-circuit study, no stability
  analysis, no protection coordination. This project reads filings; it does not model a grid.
- **You did not learn to value a project.** No revenue model, no LCOE, no capital cost, no
  financing. The project refuses to produce dollar figures precisely because you cannot support
  them.
- **You did not learn production distributed systems.** No database, no API server, no
  concurrency, no scaling, no on-call. It is a weekly batch job that writes static files, and that
  was the right architecture, but it is not distributed systems experience.
- **You did not learn front-end engineering.** Server-rendered HTML from a template plus one
  vendored map library. No framework, no build step, no state management, no accessibility audit.
- **You are not qualified to give legal advice**, including on the licensing above. You learned
  enough to identify issues, ask the right questions, and take a conservative posture. A lawyer
  would still need to look at it before money changes hands.
- **You have no external validation.** Every judgment call in the repo is yours, reviewed by you
  and by a model. Until domain experts correct it, the accuracy is unproven — and saying so is
  what makes people believe the parts you do claim.

---

# 12. The compressed version

If you have sixty seconds and someone asks what you learned:

> I learned that the hard part of an energy data product is not the pipeline, it's deciding what
> the data is not allowed to say. CAISO publishes enough to answer a lot of real questions and
> nothing at all about why projects withdraw, so I built something that answers the first and
> refuses the second. Along the way I learned that a licence on your code doesn't license your
> outputs, that a passing test suite only proves the code matches your own assumptions, and that a
> tool nobody can correct is a tool nobody has checked. The next thing I need isn't a feature — it's
> ten people telling me which numbers are wrong.

---

## Before the LinkedIn post

Three conditions, in order, and none of them are optional:

1. **The commit is pushed and CI is green.** Right now there is one unpushed commit and the
   workflows have just been SHA-pinned; a red badge on the day you post undoes the post.
2. **The repo is public and Pages is live.** A LinkedIn post linking to a 404 is worse than no
   post. Pages on a free account needs the repo public — flipping visibility and waiting for a
   successful weekly run is one sequence, not two independent steps.
3. **You have sent the ten emails and logged the replies.** Post *after* the corrections, not
   before. "I built this and three interconnection engineers have already corrected it" is a
   fundamentally different post from "I built this."

And when you write it: disclose the AI use plainly in one clause, not as a confession and not as
the headline. The interesting claim is not that you used AI. It is that you built something in a
domain where being wrong is visible, and then invited people to prove you wrong. Lead with the
invitation.
