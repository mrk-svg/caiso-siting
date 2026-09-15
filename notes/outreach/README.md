# Node Watch #1 outreach

The purpose of this send is **not** subscribers. It is corrections.

One metric: **how many of the ten replies contain a specific claim that a number is wrong.**
Nothing else on this page matters. Not opens, not replies, not compliments. A reply that says
"nice work" is a zero. A reply that says "Antelope is inside the LCA, not outside" is the whole
point of the last three weeks.

Target: **two or more corrections out of ten.** Below that, either the tool is not legible enough
for a domain expert to disagree with it, or the ten people were the wrong ten.

Log every reply in `corrections.csv`. Turn every correction into a `data-correction` issue, even
the ones you fix in five minutes, so the correction has a public trail and the person can see
their name on the fix if they want it there.

## Files

- `email.md` — the send. One version, personalised in the first line only.
- `targets.csv` — who, why them, what they would know that you don't.
- `corrections.csv` — the reply log and the one metric.

## Choosing the ten

Bias hard towards people who can contradict you. Ranked by usefulness:

1. Anyone who works interconnection at a PTO or a developer in the CAISO footprint. They can
   falsify the LCR encodings and the POI groupings immediately.
2. Consultants and owner's engineers doing pre-feasibility. They will tell you whether the seven
   questions are the right seven.
3. Former colleagues from WSP or ETS who touched CAISO projects. Warm, and they owe you a read.
4. One journalist or researcher covering queue reform. Different failure mode — they will tell
   you whether the survival caveat reads as honest or as hedging.
5. One person who knows nothing about interconnection. If the page is incomprehensible to them,
   that is worth knowing before it is public.

Do not send to ten people who will all say yes.

## `reply_type` vocabulary for corrections.csv

| Value | Meaning | Counts toward the metric |
|---|---|---|
| `correction` | Names a specific figure and says what it should be | **yes** |
| `challenge` | Disputes a method or definition rather than a figure | yes, if specific |
| `gap` | Names something missing that a public source would support | no, but log it |
| `praise` | Liked it, no specific claim | no |
| `question` | Asked something, claimed nothing | no |
| `silence` | No reply after 10 days | no |
