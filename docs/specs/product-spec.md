# Product spec

Supersedes `vertical-slice.md` and `build-spec.md`, which describe the earlier plan.
Decisions and the research behind them are on the planning map (GitHub issue #44).
Word meanings are in [`CONTEXT.md`](../../CONTEXT.md).

## What we're building

A public, map-first website that shows **how risky it is to connect a new power project at
each California substation**, based on what happened to past projects there.

- Every number can be traced to the rows it came from and is checked by code before it's
  shown.
- A person can see where the risk comes from, check it, and change it. They change the
  *inputs* (for example, leaving out a stalled project); the numbers are then worked out
  again and checked again.
- It shows history and outcomes. It doesn't simulate the grid's physics; that's a different
  kind of tool, and this one sits next to it.

## The main numbers

- **Chance of being built** within N years, and the **typical wait**, for projects like
  yours. "Like yours" means the most specific comparison group, and the most local place,
  that still has enough past projects to trust. The user can make it more or less specific.
- **Realistic MW ahead:** the MW waiting at a substation, with each waiting project counted
  only by its chance of still being built.
- **Planned grid upgrades nearby** (paid by all electricity customers) and the area's
  **cost to add room** (the operator's estimate, in 2022 prices), each in its own labelled
  box and never mixed into the odds.
- All history comes from projects that applied before the 2023 rule change, and the screen
  says so. Facts about the first batch under the new rules are shown beside it.

## Behaviour

Each line is one test, written before the code that makes it pass.

**1. Load and organise the data**
1. Loading the operator's queue reports (the main one and the 2023 batch) gives every
   project its status, dates, type, size, how far it got in the grid studies, and its place.
   Loading twice changes nothing.
2. Anything the reviewed tables don't recognise (a substation spelling, a study-progress
   value, a place) is reported, never guessed.
3. A project missing its outcome date gets an estimated date, clearly marked as estimated.
4. Each substation gets its map position from OpenStreetMap or a cited public document
   (marked "planned" if it isn't built yet), or falls back to its county. Every point names
   its source, and the share of waiting MW placed on the map is reported.
5. Planned upgrades and each area's cost to add room are attached to substations through
   reviewed tables.

**2. Chances, waits, and who's ahead**

6. For a comparison group, the product gives the chance of being built within N years and
   the typical wait, with a likely range and the number of past projects. A project still
   waiting is never counted as a failure.
7. It picks the most specific comparison group (type, then size) and place (voltage section,
   then site, then bottleneck area, then county, then California) that has enough history,
   and says which it used.
8. It refuses to give a figure beyond the history it actually has.
9. Realistic MW ahead counts each waiting project by its chance of still being built, given
   how long it has waited. Projects that connect along a line count at both of the line's
   ends, and nothing is counted twice in one number.
10. Every number comes with the exact rows it was worked out from.
11. Predictions made from past cut-off years are compared with what actually happened, and
    CI fails if that accuracy gets worse.

**3. The agent writes a checked assessment**

12. Given a substation and a project description, the agent writes an assessment made only
    of Factual Claims and Judgements, following the writing skill.
13. Every Factual Claim is checked against the data before it's shown. A number that
    doesn't reproduce, or that uses only some of the rows its query returned, is rejected.
14. A Judgement is never shown as checked.
15. An Adjustment recalculates and re-checks the affected numbers. Judgements can be
    approved, rejected or rewritten. Every change is logged, and "final" is only allowed
    once every Judgement is decided.
16. A plain request ("ignore projects stuck since 2019") becomes a proposed Adjustment that
    applies only after a person confirms it.
17. Deliberately broken claims are all caught, and answer-key questions get the right
    numbers and rows.

**4. The map app**

18. The map shows substations coloured by realistic MW ahead, with unplaced ones listed by
    county.
19. A substation page shows its numbers, the history ladder, the upgrades box and the cost
    box. Clicking any number shows its source rows.
20. Adjusting, reviewing and asking all work from the page.

**5. Ship it**

21. The public site loads about 10 pre-generated assessments instantly. Live runs are capped
    per visitor and per day, with an off switch.
22. Claude, with the add-on (MCP server and skill) installed, produces an assessment whose
    numbers pass the checker.

Already built and kept: the spending limits and the leaked-key scan.

## Questions settled inside their ticket

- **Ticket 1:** keep or rewrite each existing test (the test review).
- **Ticket 4:** the product's name, its look, how the history ladder is shown, how unplaced
  points appear, the review experience, and whether public transmission lines are shown
  as a background layer. Settled with a prototype first.
- **Ticket 5:** what the public site saves and shares, and what the Claude add-on exposes.

## Not in scope

Grid physics (power-flow simulations), per-project upgrade costs, large electricity users
such as data centers, solar output estimates, and a "check a chatbot's answer" feature.
