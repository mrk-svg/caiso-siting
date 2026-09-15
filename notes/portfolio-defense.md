# Portfolio defense: how to use this repository in an interview

Written for the person who has to answer questions about it, not for a reader of the code.

---

## 1. What is actually being demonstrated

A résumé is a list of claims. Fifteen companies, four countries, three continents. Every line of
it is something a hiring manager has to take on trust, and the trust has to come from somewhere —
usually a credential, a brand name, or a referral. With no PE, no FE, and no master's, two of
those three levers are unavailable and the third is slow.

This repository is the fourth lever, and it is the only one that does not depend on anyone's
permission: **an artifact a stranger can interrogate.**

That is not the same as "a project on GitHub". Most portfolio projects are tutorials with the
serial numbers filed off, and hiring managers know it. What makes this one different is that it
sits in a domain where the interviewer cannot check your work by pattern-matching. If you hand a
CAISO interconnection engineer a node page, they do not evaluate your Python. They read the page
and decide within about thirty seconds whether you understand their world. Everything below is
about winning those thirty seconds.

### The energy-engineer lens

A person who has spent five years in interconnection reads this and asks: does he know the
difference between a request and an allocation? Does he know TPD is a separate process from the
cluster study? Does he know a withdrawal is usually a portfolio decision, not a grid verdict?

The repository answers all three without you saying a word, because those distinctions are
encoded in the column names. `tpd25_alloc_mw` versus `tpd25_unalloc_mw`. "Cluster 15
deliverability is requested, not allocated" sitting in the footer of every page. Known limitation
#3 saying out loud that withdrawal ≠ failure of the node.

Those lines are the tell. Someone who had only read about the queue would have built a single
"MW at this node" number and been proud of it.

### The software-engineer lens

A person who has spent five years shipping data products reads this and asks a different set of
questions, and they are mostly about failure. What happens when the input file changes shape?
What happens when a join has a tie? What does the page show when the data does not support the
number? Who finds out when it breaks?

The answers here are unusually good for a solo project, and they are the answers to give:

- **Failure is loud.** The header-drift guard breaks a parse rather than silently producing wrong
  columns. A corrupt EIA zip yields empty columns and a logged warning rather than taking down
  the whole `nodes` build.
- **Unknown is a type, not a zero.** `fact()` distinguishes *dimmed* (too few projects to quote)
  from *undefined* (denominator does not exist) from *not public* (CAISO does not publish it)
  from *not here yet* (we have not built it). Four states where most tools have one, and the
  blank is the most common lie in data products.
- **The pipeline is observable.** Every output row carries `source_file`, `source_run_date`,
  `pipeline_commit`, `pipeline_run`. Any figure on any page can be traced back to a file and a
  commit. That is provenance, and almost nobody does it.
- **It runs unattended and it knows when to stay quiet.** The weekly job only commits and only
  opens an issue when CAISO actually posted a new run date. Automation that fires every week
  regardless of whether anything changed gets muted, and a muted pipeline is a dead pipeline.

### The two lenses converge on one word

**Restraint.** In energy terms: refusing to publish a number the filings do not support. In
software terms: refusing to let a null become a zero. It is the same discipline wearing two
costumes, and it is the thing that is genuinely hard to teach. Lead with it.

---

## 2. The set-pieces

Three stories. Each has a sixty-second version for a screen and a five-minute version for a
technical round. Practise the sixty-second version until it is boring to you.

### Set-piece A — TPD allocation groups

**Sixty seconds.** CAISO's 2025 TPD allocation results tell you how much deliverability each
request asked for and how much it got. The obvious build is one number per node: MW refused. I
built that first and it was useless, because it answers a question nobody asks. The allocation
report splits requests into four groups — A, executed PPA or LSE own-load; B, shortlisted or
negotiating; C, already in commercial operation; D, no PPA at all, under section 8.9.2.3. Once
you split the refusals by group, the same raw number means opposite things. A node refusing group
D projects is behaving exactly as the tariff intends: no offtake, no priority. A node refusing
group A is telling you something structural about the transmission there, because those are
projects with a signed PPA that still could not get deliverability. So the page carries
`tpd25_denied_ppa_mw` separately from total refusals. Same data, and the split is the entire
signal.

**Five minutes — what to add.** Why you went to the allocation report rather than inferring the
groups. Why you dropped the idea of a single "deliverability difficulty" score (it would have
averaged A against D and destroyed the only useful distinction). The 2024 bug where you were
counting rows instead of distinct projects, and how you found it.

**What this proves to each lens.** To the energy engineer: you read the tariff, not a summary. To
the software engineer: you chose a schema that preserves a distinction instead of a schema that
looks tidy.

### Set-piece B — the survival regime caveat

**Sixty seconds.** I built Kaplan–Meier survival curves for queue cohorts — of the projects that
entered in cluster N, what fraction was still active after M months. The curves looked great, and
they were misleading. C14 and C15 went through materially different processes: C14 ran under the
FERC-approved September 2021 special procedures with roughly 373 requests, and C15 ran under the
new intake scoring that cut 541 requests to 145 before study. If you plot those two curves on the
same axes, the reader infers a trend in developer behaviour, when what they are actually seeing
is a change in CAISO's process. So every curve now carries a regime annotation naming the window
and the process, and the findings text repeats the caveat. The curve is less impressive and more
true.

**Five minutes — what to add.** The censoring subtlety: C15's censor date started as the report
posting date, and a review found the file could contain a withdrawal *after* that date, which
would have quietly understated attrition. It is now the later of the two, computed per run. This
is the detail to spend time on, because censoring is where survival analysis goes wrong and
knowing that is a real signal.

**What this proves.** To the energy engineer: you know the queue reform history well enough to
know when a comparison is illegitimate. To the software engineer: you understood that the honest
version of a chart is worth more than the impressive version — and you shipped the honest one
after the impressive one already worked.

### Set-piece C — the bug you found in your own code

Use this one when asked about code quality, testing, or mistakes. It is stronger than either of
the above because it is about you, not about the domain.

**Sixty seconds.** I added an EIA-860 connector so each node shows what is already built there,
joined by distance. It worked, the tests passed, the numbers looked plausible. Then I ran an
adversarial review over it and found that nodes whose position is only a transmission-line
midpoint were eligible as nearest neighbours, and distance ties were resolved by DataFrame row
order. So plants were being attributed to the wrong substation — not crashing, not warning, just
confidently wrong. Restricting the join to nodes with real positions moved San Bernardino from
showing nothing to showing 1,064 MW. Nothing in my 337 tests would have caught it, because I had
tested the code against my own assumptions and the assumption was the bug.

**The lesson to state.** A passing test suite proves the code does what I think it should. It
proves nothing about whether what I think is right. That is why the project now publishes an
explicit list of what it does not know, and why the contributing guide asks strangers for wrong
numbers instead of pull requests.

---

## 3. Questions you will be asked, and honest answers

**"You used AI to build this. What did you actually do?"**
Do not get defensive and do not undersell it. The honest answer: I specified it, I made every
domain judgment in it, and I reviewed it adversarially until it stopped being wrong. The AI wrote
a lot of the Python. It did not know that TPD groups matter, that C14 and C15 are not comparable,
or that a line-midpoint node should not win a distance join — I knew those, and finding them is
the job. Then offer the test: ask me why any column is named what it is named.

**"You're not a PE. Why should I trust your judgment on siting?"**
You shouldn't, and the tool says so on every page. It is a screening tool built from public
filings, and it refuses to produce anything that would require a stamp — no power flow, no cost
estimate, no recommendation. Knowing where that line is, and building the disclaimer into the
render path rather than the footer, is itself the answer to your question.

**"Does anyone use it?"**
No, and I will not pretend otherwise. It has run weekly since [date], it has zero external users,
and the next thing I am doing is putting it in front of ten people who will tell me which numbers
are wrong. I would rather show you a tool with no users and honest numbers than one with a
landing page and invented ones.

**"Why no overall score? A ranking would be more useful."**
It would be more sellable and less useful. A composite hides its weights, so nobody can tell
whether a node ranks well because of deliverability or because of land. It also cannot be
checked: you can argue with a number that traces to a filing and you cannot argue with a 73. Every
commercial tool in this space sells the score, which is exactly why a free tool should not.

**"This is just ETL with a static site generator."**
Mostly, yes — and the hard part was never the T. The hard part is that CAISO publishes a county
column containing "king", "San Bernadino" and "Kings and Fresno"; that substation names collide
across utilities so MESA in SCE is not MESA in PG&E; that a substation has no coordinates in any
public file, so positions come from OSM, CEC line geometry and hand overrides, each tagged with
how it was derived. The engineering is in deciding what to do when the data is ambiguous, and
doing the same thing every time.

**"How would you work on this with a team?"**
Name the actual gaps: the hand-built CSVs need an owner and a review process because they encode
judgment; the test suite needs property-based tests over the joins, not just examples; the
review-by-adversary step I run manually should be a CI gate. Then say what you would not change:
the traceability contract and the refusal to publish unsupported figures are the product, and
they get harder to hold as a team grows, so they go in the contributing guide on day one.

**"What would you build next if this were your job?"**
The LMP layer, honestly scoped. Right now only a minority of nodes have a confirmed OASIS pricing
node, so the "what is power worth here" question is unanswered for most of the map. EIA-860
publishes each plant's reported LMP node designation, which gives a cross-check against the
hand-built mapping. That is the next thing that changes a decision. A prettier UI is not.

---

## 4. What not to claim

- Do not call it a platform, a product, or a startup. It is a tool with no users.
- Do not say it predicts anything. It does not, and the code refuses to.
- Do not quote a figure you have not re-derived that morning. The data changes weekly.
- Do not imply CAISO affiliation, endorsement, or data access beyond what is public.
- Do not say "we". You built it alone with AI assistance; say that.
- Do not claim the dollar value of a decision it could improve. There is no such number.

---

## 5. The ninety-second open

When someone asks "tell me about the project":

> CAISO publishes everything about the interconnection queue and none of it is usable. The
> queue report is a spreadsheet with thousands of rows and no geography; deliverability results
> are in a different workbook; local capacity areas are in a PDF; what is already built is in an
> EIA form. Every developer I know rebuilds the same join in Excel and throws it away.
>
> So I built a pipeline that does it once a week and publishes one page per interconnection node.
> Seven questions, in the order a developer asks them: can you get in, who is ahead of you, do
> projects leave after they see the costs, is it deliverable, is the power worth anything, does
> the land pass a first screen, how long does it take.
>
> The constraint I set was that every number traces to a source row, and anything the filings do
> not support says so instead of guessing. That rules out most of what a commercial tool would
> sell — there is no score, no forecast, no dollar figure. What is left is smaller and checkable.
>
> It has no users yet. That is the next problem, and it is not a code problem.

Then stop talking. If they want the demo, the node page does more work than you will.

---

## 6. Which roles this is evidence for

**Interconnection / origination analyst.** Strongest fit. The set-pieces are literally the job.
**BESS development engineer.** Use set-piece A and the deliverability framing; add the storage
churn and the EIA storage MWh layer.
**Grid data / energy analytics engineer.** Lead with the software lens — provenance, the four
unknown states, unattended operation, adversarial review.
**Owner's engineer / diligence.** Lead with the refusals: no score, no causal claim, no invented
figures. That is diligence temperament, and it is rarer than the technical skill.

Whichever it is, the close is the same, and it is the only sentence in this document that has to
be said exactly: *I would rather show you a small tool with honest numbers than a large one with
convenient ones.*
