# Rates are worked out per queue-entry year, never over all years at once

**The problem.** A dropout rate taken over the whole table at once comes out too low.
Projects that joined in the last few years make up most of the rows, and most of them haven't
had time to either drop out or get connected yet. For example, counting LBNL's statuses
directly gives about 63% withdrawn, while the California Public Advocates report gives about
71%. That gap comes from the two being worked out differently, not from bad data. Comparing
them directly would have made the loader's cross-check report a correct load as broken.

**The decision.** Group projects by the year they joined the queue (the year of `q_date`,
called the "vintage"). For each year, report `withdrawn / (withdrawn + operational)`, which
only counts projects that have reached an outcome, together with how many are still waiting.
Headline figures come from years old enough that most projects have reached an outcome, and
the cut-off year is stated.

## What follows from this

`get_historical_timeline` has the opposite bias. It only measures projects that got
connected, so its median is the typical wait *among the ones that made it*, not what a
project joining today should expect. The function returns the share of projects that made
it alongside the median, so the warning travels with the number instead of sitting in a
README section nobody reads.
