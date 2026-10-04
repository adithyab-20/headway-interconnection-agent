# The model returns structured claims; the text is built from them, never parsed back

**Status:** accepted. This is the design for build step 4 (checking every number).

**The problem.** The original plan had the model write prose, and code would then pull the
numbers back out of the text to check them. That turns checking into a language-parsing
problem. Its typical failure is marking a correct number as wrong:

- rounding ("about 450 MW" against 448.3),
- unit changes (years against days),
- and above all numbers the model worked out itself, like a sum or a percentage. These
  don't appear in any single source row, so a text checker would mark them wrong even when
  they're right.

Worked-out numbers are most of what a risk assessment says. So under the original plan, most
of the report would end up "unchecked" and sent for human review, which defeats the point of
the project.

**The decision.** Turn it around. The model's Assess step returns structured claims only.
Each claim carries its sentence, the numbers it states, how each number was worked out, and
the source rows it cites. Checking is then a database lookup plus redoing the arithmetic,
with a clear pass or fail every time. The final text is built by joining the sentences of
claims that passed. A failed claim can't appear as checked, because the code that builds the
text reads the check result.

## How a number can be worked out: a fixed list

`derivation` must be one of five values: `direct` (copied from one row), `sum`, `count`,
`median`, or `ratio`. Each has exactly one checking function. Anything else fails outright.

How close is close enough is set per unit and written down in the repo: MW to the nearest
10 or within 5%, years to one decimal place, percentages to the whole point. Without a
written rule, "close enough" is just a feeling.

`source` is a fixed list too: `caiso_raw` or `lbnl`, spelled exactly like that everywhere.

## Medians and analysis results are compared, not recalculated

`median`, percentiles, and the outputs of the four analysis functions stay on the list. But
they're checked by confirming that the claim quotes exactly what the function returned, not
by recalculating them. Recalculating would mean a claim has to cite every row in the group
(235 row IDs for a CAISO wait-time figure) just so the checker can repeat work that tested
code already did. That checks the wrong thing. The analysis functions are ordinary tested
code. The model is the part that needs checking.

## The model can't pick and choose rows

Every query the agent runs gets an ID (`tool_call_id`), and the full list of row IDs it
returned is saved in a query log. Each number in a claim names the query it came from, and
the checker compares the rows the claim cites with the rows that query actually returned.

- For `sum`, `count`, `median`, and `ratio`, they must be exactly the same rows.
- For `direct`, the cited row must be one of them.

So an agent that cites 2 of the 3 rows a query returned, and adds those 2 up correctly,
still fails. Add the rule that all filtering happens in SQL (the agent never takes a broad
result and filters it in its head), and picking convenient rows becomes impossible rather
than just discouraged.

## What the checks still can't prove

The checks prove the arithmetic, where each number came from, and that a claim used every row
its query returned. They do **not** prove the query was the *right* one: the wrong
substation, a missing filter, or the wrong tool. In that case every number checks out
perfectly while the assessment is about the wrong place.

An offline test closes part of that gap: answer-key test cases check that the agent picked
the right rows, wherever the right rows can be pinned down exactly. The two work together;
neither replaces the other. What's left after both is judging whether two projects are
really comparable at all. That's a human call, and the README says so.

## Rejected: promptfoo for measuring the AI reviewer

We considered promptfoo for running the AI reviewer (the second model that grades the
wording-based parts of an assessment) against the set of human-graded samples. Rejected. The
number checker is plain Python, where promptfoo adds nothing. Measuring the reviewer is
about 40 lines of pytest over a labelled CSV, and the labelled CSV, which is the real work,
is needed either way. A new configuration language and a web interface would be hard to
justify, and an unjustified tool hurts the project's credibility more than it helps.
Reconsider only if several reviewer prompts or models need comparing side by side across the
labelled set.
