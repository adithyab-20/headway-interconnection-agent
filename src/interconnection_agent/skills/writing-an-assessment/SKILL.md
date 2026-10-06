---
name: writing-an-assessment
description: Write a checked assessment of how risky it is to connect a proposed power project at a California substation, from public queue data. Every number is quoted from a lookup and checked by code; every interpretation is a Judgement a person decides on.
---

# Writing an assessment

You are writing a short assessment of how risky it is to connect one proposed power project
(solar, wind, battery, gas) to the grid at one California substation. The evidence is what
happened to past projects in the grid operator's queue: how many were built, how long they
waited, and how much is waiting at the substation now.

Code checks every number you state before anyone reads it. A number that doesn't reproduce
from the data is rejected and never shown. Write so your numbers pass.

## 1. Look things up

Use the lookups; never work a number out from memory or in your head.

- `chance_of_being_built`: the chance that projects like this one are built within N years
  of applying, the typical wait, and how many past projects that rests on. Ask for 5 and 10
  years. It picks the most specific comparison group with enough history and says which;
  report that group by name. If it says the group has too few projects to rely on, say so.
- `realistic_mw_ahead`: the MW waiting at the substation, each project counted only by its
  chance of still being built, and the 2023 batch's waiting MW as its own figure.
- `list_projects`: projects at the substation by status (waiting, built, withdrawn), rules
  (old, 2023 batch, any) and type. Do every filtering in the lookup. Never take a wider list
  and pick rows out of it yourself.

## 2. Write claims, not prose

Submit with `submit_assessment`: a list of claims, each one of exactly two kinds.

**Factual Claim** (`"kind": "factual"`): one sentence stating numbers. Put each number in a
numbered slot, `{0}`, `{1}`, ..., and give one entry in `values` per slot. Code fills the
slots with the checked numbers, number and unit together ("1,234 MW", "38 projects",
"12%", "6.2 years"), so don't write the unit after a slot. Write no other numbers in the
sentence, except names (such as "Whirlwind 230 kV" or "the 2023 batch") and numbers you
asked a lookup for (such as "within 10 years").

Each value names:

- `value`: the number, in the unit given. Round as you like within the margin: MW to the
  nearest 10 or within 5%, years to one decimal, percentages to the whole point, counts
  exactly.
- `unit`: `MW`, `years`, `%` or `projects`.
- `tool_call_id`: the lookup it came from. `source`: `caiso_raw`.
- `of` and `derivation`: either a figure the lookup returned, with that figure's derivation
  (for example `"of": "chance", "derivation": "ratio"`), or a column of the lookup's rows:
  `"of": "projects", "derivation": "count"`, or `"of": "mw_to_grid"` with `sum`, `median` or
  `direct` (one row's value).
- `source_row_ids`: for anything worked out from the lookup's rows, every row the lookup
  returned (a `direct` quote: the one row). Using only some of them is rejected, even when
  the arithmetic is right. For a figure, leave it out: its rows are attached for you.

**Judgement** (`"kind": "judgement"`): an interpretation the numbers can't prove (a likely
cause, whether the comparison is fair, what it means for this project). No numbers and no
`values`; list the Factual Claims it rests on in `based_on`. A person approves, rejects or
rewrites every Judgement, so make each one a single point they can decide on.

Nothing else: no summary, no headings, no recommendation that isn't a Judgement.

## 3. What a good assessment covers

In five to eight claims:

1. The chance of being built within 5 and 10 years for projects like this one, with its
   likely range, the comparison group, and how many past projects it rests on.
2. The typical wait, and that it only counts projects that were built.
3. Realistic MW ahead at the substation against the raw MW waiting there, and the 2023
   batch's waiting MW beside it (never added in: no history says how likely those are).
4. One to three Judgements on what this means for the project.

All history comes from projects that applied before the 2023 rule change. Say so once.

If a claim comes back rejected, read why, fix it or leave it out, and submit again.

## 4. Answering a person's request about an assessment

A person reading the assessment may ask something ("how many projects withdrew here?") or
ask for a change ("ignore projects stuck since 2019").

- A question: look it up and submit new claims, with ids not already used, exactly as above.
- A change to what goes into the assessment: call `propose_adjustment` with the projects to
  leave out (by id, or `waiting_since_year` for projects still waiting that joined the queue
  in that year or earlier) and the reason in the person's words. You only propose: code
  lists the exact projects, and nothing changes until the person confirms. Never type a
  new number in place of a checked one.
