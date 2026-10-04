# Plan: the first working version

**What this covers:** build steps 1–4 of [`build-spec.md`](build-spec.md) (load the data,
set up the database, build the agent and its analysis functions, check every number), plus
the first 10 answer-key test cases. Output is JSON and command-line only; there is no
dashboard yet. This is the first point at which the project does its whole job end to end
and is worth showing someone.

**Decisions this plan relies on** (each has a short write-up in `docs/adr/`):

- [0001](../adr/0001-two-column-location-hierarchy-and-per-source-views.md): how locations
  are stored, and why each dataset is read through its own database view.
- [0002](../adr/0002-rates-are-cohorted-by-vintage.md): why rates are worked out per
  queue-entry year instead of over all years at once.
- [0003](../adr/0003-claims-are-generated-structured-not-parsed-from-prose.md): why the
  model hands back structured claims instead of prose, and how each number gets checked.

Word meanings follow [`CONTEXT.md`](../../CONTEXT.md).

---

## The problem

Someone deciding where to build a solar farm, wind farm, or battery (a "siting analyst")
needs to know how hard it will be to connect it to the grid. Every grid operator keeps a
public waiting list of projects asking to connect, called the **interconnection queue**.
From that list the analyst wants three answers:

1. **How crowded is the connection point?** How many projects are already waiting to
   connect at the same substation?
2. **How long does it take?** How long did similar projects actually wait before they
   started producing power?
3. **How often do projects give up?** What share of similar projects dropped out of the
   queue instead of getting built?

The data is public, but it is not usable as published. California's grid operator (CAISO)
spreads projects across three spreadsheet tabs with the column headers on row 4. A single
row can list up to three fuel types. The substation name is typed by hand, so the same place
shows up as "Devers Substation 230kV Bus" and "Devers Substation 230 kV". Answering even a
simple question means hours of spreadsheet work.

The analysis after that is where the real mistakes happen:

- **Counting the projects ahead of you overstates the competition**, because most of them
  will drop out.
- **A dropout rate taken over all years at once comes out too low.** Projects that joined
  recently haven't had time to drop out yet, but they still count in the total.
- **The typical wait to start producing power comes out too short.** It can only be measured
  for projects that finished. Projects still stuck in the queue after nine years aren't in
  the number at all.

An AI model will answer all of these questions in fluent prose, and some of the numbers will
be made up. When real money depends on the decision, a confident paragraph with numbers you
can't trace to a source row is worse than no answer, because you can't tell it apart from a
correct one.

## The solution

An agent that writes an interconnection-risk assessment in which **every number is linked to
the exact source rows it came from, and checked by code before anyone reads it.**

The usual setup is that a model writes prose and something checks it afterwards. This
project turns that around:

1. The model does not write prose. It hands back **structured claims**. Each claim says what
   number it states, how that number was worked out (copied from a row, added up, counted,
   and so on), and which rows it came from.
2. Ordinary code then **checks each claim**. Do the cited rows exist? Does the stated
   working-out reproduce the number? Did the claim use *every* row its query returned, or
   only a convenient few?
3. The readable text is **built only from claims that passed**. A claim that failed can't
   show up as checked, because the code that builds the text reads the check result.

The expert judgement lives in tested Python, not in the prompt. Dropout rates are worked out
per queue-entry year. Wait times always come with a warning that they only count projects
that finished. Crowding compares megawatts (MW) waiting at a substation with the MW that has
actually been connected there before. The analysis functions add these warnings themselves,
so the model can't leave them out.

Where the code can't check something, the output says so plainly instead of implying it was
checked.

## What people need from it

**An analyst getting an answer**

1. Ask about a substation by name in plain language, without knowing the queue's internal
   IDs.
2. See how many projects at that substation are waiting, finished, and dropped out, not
   just one total.
3. See total MW waiting at the substation next to the MW actually connected there before, to
   judge how crowded it really is.
4. See how long similar projects actually took to start producing power, based on real
   history rather than the dates developers predicted.
5. See that as a middle value with a typical range (median, 25th and 75th percentile) rather
   than one average that hides the spread.
6. See a dropout rate for similar projects, to judge how much of the queue ahead will never
   be built.
7. See California-only figures and national figures side by side, to tell local conditions
   apart from the national picture.
8. Ask about a county or one of CAISO's planning areas when there is no specific substation
   yet.
9. Get an assessment written as connected prose rather than a table dump, ready to use in a
   memo.

**An analyst trusting the answer**

10. Every number lists the rows it came from, so any figure can be checked by hand.
11. Every claim is marked checked, not checked, or contradicted.
12. A checked claim can be opened to see the actual source rows, so the check is something to
    inspect and not just a badge to trust.
13. A claim whose arithmetic doesn't reproduce is left out entirely, not shown with a
    warning, so a wrong number never reaches a memo.
14. A figure based on very few projects says so.
15. Wait times are always labelled as counting only projects that finished, so they read as
    too optimistic.
16. Dropout rates are given per queue-entry year, with the number of projects still
    undecided, not one rate over all years that understates the truth.
17. Projects whose substation name couldn't be matched are counted and reported, so leaving
    them out quietly doesn't skew a crowding figure.
18. A question with no matching rows gets an explicit "no matching evidence", not a
    broadened question or an invented answer.
19. Claims that need a person to look at them are flagged, so they can go to someone with
    domain knowledge.
20. The tool states that it covers power plants connecting to the grid only, not large
    electricity users like data centers.

**A developer working on the data**

21. CAISO's three tabs load into one `projects` table, so later code sees one layout.
22. Up to three (fuel type, MW) pairs per project are stored as separate rows in a second
    table, so hybrid projects aren't crammed into repeated columns.
23. The grid operator (`iso`) and the planning area inside it (`study_region`) are separate
    columns, so a national comparison and a within-California comparison can't be mixed up.
24. Rows from Berkeley Lab's national dataset (LBNL) for its "West" and "Southeast" areas are
    stored with `iso = NULL` and the local utility area in `non_iso_entity`. Those areas have
    no grid operator, and must never be treated as if they did.
25. The original substation text is kept next to the cleaned-up version, so the source cell
    can always be shown.
26. Substation spellings are grouped through a checked-in table that a person has reviewed,
    so grouping is predictable and can be audited.
27. Fuzzy name matching is only used offline, to suggest groupings for review. Nothing that
    sits under a checked number ever relies on a guessed match.
28. Substation names that can't be matched are flagged, not guessed, so coverage is a
    reported number and not a hidden assumption.
29. Loading uses each source's own project IDs, so loading twice never creates duplicates and
    the row IDs stored in test cases stay valid.
30. Each dataset has its own database view with the source filter built in, so forgetting a
    `WHERE` can't double-count a CAISO project that appears in both datasets.
31. Every load reports how many rows were loaded, skipped, and unmatched, and why, so data
    quality is measured and not assumed.
32. Rates calculated from CAISO's own file are checked against LBNL's copy and against a
    published California Public Advocates report, so a mismatch shows up as a failing test.
33. The mapping from each source's status words ("Withdrawn", "In Service", ...) to this
    project's statuses lives in plain configuration, so a reviewer can question it without
    reading loader code.

**A developer working on the agent and the checks**

34. All filtering happens in SQL. The agent never takes a broad result and picks rows out of
    it in its head, then cites the ones it picked.
35. Every query the agent runs gets an ID, and the full list of rows it returned is saved,
    so the checker can compare what a claim cites with what the query actually returned.
36. The model returns structured claims, not prose, so checking is a database lookup and not
    a text-parsing problem.
37. The ways a number can be worked out form a fixed list (`direct`, `sum`, `count`,
    `median`, `ratio`), with one checker each. Anything not on the list fails outright
    instead of slipping through.
38. How close a number must be to count as correct (for example, MW to the nearest 10) is
    written in a table in the repo, so it's a rule, not a judgement call.
39. Rounding and restating units (days as years) pass the check, so natural wording isn't
    marked wrong.
40. Sums and ratios can be checked, so the most common kinds of number aren't left
    unchecked.
41. Medians and the analysis functions' outputs are checked by confirming the claim quotes
    the function's result exactly. The model is the thing being checked, and the functions
    already have their own tests.
42. A claim must cite exactly the rows its query returned. Leaving one out fails even if the
    arithmetic on the remaining rows is right.
43. Readable text is built only from checked claims, so an unchecked number can't reach the
    reader.
44. The analysis functions are tested before any agent code is written, so a bug found later
    is never two bugs stacked on each other.
45. A set of deliberately broken claims measures how often the checker lets a bad claim
    through and how often it rejects a good one, instead of just asserting that it works.
46. Ten test questions have answers written independently by hand, so a bug shared between
    the agent and its test can't make the test pass.
47. These tests run in CI on every pull request, so the build catches a regression before a
    person has to notice it.
48. Each assessment has a limit on tokens and on model calls, so an agent stuck in a loop
    fails the request instead of running up a bill.
49. A monthly spending cap is set in the Anthropic console before the first agent run, so
    cost is limited by a setting and not by someone watching it.
50. Logs are structured and each assessment records its own measurements, so speed, cost,
    and how many claims passed are visible from the start.

**A reviewer**

51. The README says exactly what the checks prove and what they don't, so the claim can be
    judged rather than taken on trust.
52. Every reported number comes with the command that reproduces it, so measurement and
    estimate can be told apart.
53. The reasons for leaving out certain technologies are written down, so the scope reads as
    a decision and not an oversight.
54. The loader's rules for cleaning up names and statuses are documented, because that is the
    hardest part of the data work to judge.
55. The README answers "why an agent and not a script?" directly, so the small role left for
    the model reads as a choice.

## How it's built

**Parts of the code**

- **`ingest`**: reads the CAISO workbook (three tabs, headers on row 4) and the LBNL file
  (the `03. Complete Queue Data` sheet, headers on row 2) into the shared table layout.
  Returns an `IngestReport` with, for each source, rows read, rows written, rows skipped and
  why, and MW whose substation couldn't be matched.
- **`poi`**: looks up each substation name in the reviewed table, by exact match only, while
  the program runs. The script that *suggests* new groupings (using fuzzy matching) is a
  separate developer tool that the running program cannot import.
- **`analysis`**: the four analysis functions, plus general statistics like the median. Each
  returns its result, the rows it came from (its "provenance"), and any warnings.
- **`agent`**: a LangGraph graph with the steps Plan → Retrieve → Analyze → Assess → Check →
  Render.
- **`verify`**: the number checker. A plain function of the claims, the query log, and the
  database: no model, no network.
- **`api`**: a FastAPI service. `POST /assess` returns a job ID, and `GET /assess/{job_id}`
  returns the status and, when finished, the result. A Celery worker runs the agent.

**Database tables** (decision [0001](../adr/0001-two-column-location-hierarchy-and-per-source-views.md))

- `projects`: `source`, `native_id`, `status`, `q_date`, `proposed_online_date`,
  `actual_online_date`, `withdrawn_date`, `ia_date`, `county`, `state`, `iso`,
  `study_region`, `non_iso_entity`, `raw_poi`, `normalized_poi`, `poi_unmapped`, `utility`.
- `project_resources`: one row per (project, fuel type, MW), so hybrid projects don't need
  repeated columns.
- Row IDs are the sources' own IDs (`CAISO-0123`, LBNL's identifier), never auto-numbers.
  Test cases store these IDs and they must stay valid when data is loaded again.
- The views `caiso_projects` and `lbnl_projects` each have `WHERE source = ...` built in.
  All analysis reads a view. The one exception is the cross-check between datasets, which
  needs both sources at once and so reads the main table.
- `source` can only be `caiso_raw` or `lbnl`, spelled exactly like that everywhere.

**What the analysis functions promise** (decision [0002](../adr/0002-rates-are-cohorted-by-vintage.md))

- `source` must always be given. There is no default.
- `get_withdrawal_rate` returns, for each queue-entry year, `withdrawn / (withdrawn +
  operational)` and the number of projects still undecided. It does not offer one rate over
  all years.
- `get_historical_timeline` returns the median and the 25th and 75th percentile, and its
  result always includes the warning that only finished projects are counted.
- `get_local_saturation` only works with `caiso_raw`, because LBNL doesn't record which
  substation a project connects to in a usable way. Asking for it with `source=lbnl` raises
  an error. An empty result would read as "no crowding here", which is the opposite of the
  truth.
- Every function reports the projects it left out because their substation couldn't be
  matched, as a count and in MW.

**What a claim looks like** (decision [0003](../adr/0003-claims-are-generated-structured-not-parsed-from-prose.md))

- The Assess step returns structured claims only. Each value carries `value`, `unit`,
  `derivation`, `source_row_ids`, `tool_call_id`, and `source`.
- `derivation` is one of `direct | sum | count | median | ratio`, with one checker each.
  Anything else fails.
- `median` and the four analysis functions' outputs are checked by confirming the claim
  quotes the function's result, not by recalculating it.
- The table of how close is close enough is per unit, kept in the repo, and versioned.
- All-rows check: the rows a claim cites are compared with the rows its query (`tool_call_id`)
  returned. For `sum`, `count`, `median`, and `ratio` they must be exactly the same rows. For
  `direct` the cited row must be one of them.
- The final text joins together the text of claims that passed, and nothing else.

**Queries the agent can run**

- SQL queries with parameters, and a required `source`. Every call saves its
  `tool_call_id` and the full list of row IDs it returned to the query log.
- All filtering happens in SQL. The agent never filters a broader result itself.

**Grouping substation names, and when to stop**

Fuzzy matching suggests groups offline → a person reviews them → the reviewed table is
checked in with a version → the loader applies it. A name with no reviewed match gets
`normalized_poi = NULL` and `poi_unmapped = true`; it is never guessed. Stop when unmatched
names cover less than 2% of the MW waiting in the queue, or after one day of work, whichever
comes first. The coverage percentage goes in the README. A test compares the groupings with
LBNL's own substation names for the projects in both datasets and reports any disagreement.

**Keeping costs under control**

The API key lives in `.env`, and `.env.example` is checked in with blank values. CI scans for
leaked keys. A spending cap is set in the Anthropic console before the first agent run. Each
assessment has token and model-call limits in code. Pull requests run only the cheap tests.
The nightly run that repeats each test several times stays off until the spending cap is
confirmed.

## How it's tested

**What a good test looks like here.** Tests check things you can see from outside: what's
in the database after a load, the numbers and warnings a function returns, whether the
checker passes or fails a claim, and the claims a run produces. They don't check which
internal functions were called, the wording of prompts, or internal structure. The checker
is the one place where near-complete coverage is worth it. It is the part the whole project
depends on, and it gives the same answer every time.

**Where tests attach** (agreed with the developer)

1. **Loading the data**: `run_ingest(workbook_paths, db) → IngestReport`, run against a
   real Postgres loaded from the saved spreadsheets. Checks row counts, the per-fuel rows,
   how `iso` and `study_region` are filled in, the West/Southeast handling, that loading
   twice changes nothing, and how unmatched substations are counted. The cross-checks against
   LBNL and the Public Advocates report also live here, with their allowed margins written
   down.
2. **Analysis functions**: called directly against a loaded database. Checks that rates come
   per queue-entry year with the undecided count, that the "only finished projects" warning
   is *in the return value*, that the crowding function refuses `source=lbnl`, and that left-out
   projects are reported.
3. **The number checker**: `verify(claims, trace, db) → VerificationResult`, fed hand-made
   claims and deliberately broken copies of them.
   - *Must pass:* the same decimal written differently, rounding within the allowed margin,
     row IDs in a different order, a correct direct quote.
   - *Must fail:* a value outside the margin; a missing or extra row; **citing only some of
     the returned rows even when the arithmetic on them is right**; MW and GW mixed up; the
     wrong working-out label (says `sum` but is a `ratio`); an LBNL row cited as
     `caiso_raw`; both datasets' copies of one project mixed together; a dropped-out project
     in a claim about waiting projects; a value citing no rows; a `tool_call_id` that isn't
     in the query log.
   - Reports how often a bad claim got through and how often a good one was rejected.
4. **The agent end to end**: `run_assessment(prompt) → claims + check result` on the 10
   answer-key cases. The graders for "are the numbers right?" and "did it pick the right
   rows?" read **the same saved run**; the agent isn't run twice.

**Keeping test answers independent.** The expected answers for the test cases are plain
Postgres queries, written by hand from what each question means. Graders must not import the
analysis functions or call the number checker. If they did, a bug would show up on both sides
and the test would pass, which only proves a function agrees with itself. This duplication is
on purpose. Removing it to avoid repetition would be a mistake, and this note is here so
nobody "fixes" it later.

**Real Postgres, never a fake database.** The guarantee that nothing gets counted twice is
enforced by the database views themselves. A fake database would leave that guarantee
untested exactly where it matters. Tests use a Docker Compose Postgres loaded by the real
loader, with no separate snapshot setup.

**Light testing** at the API: one test that `POST /assess` returns a job ID and `GET`
eventually returns the report, with the agent replaced by a stand-in.

**Earlier work to follow:** none. This is a new repo, so these test points set the pattern.

## Not in this version

- **Dashboard** (build step 7): JSON and command-line output only for now.
- **The AI reviewer and the human grades it's measured against** (build step 6): this needs
  the agent's written output to settle down first.
- **Test cases 11–30**: this version builds the test setup and the first ten cases.
- **Monitoring beyond structured logs**: no metrics panel, no Prometheus or Grafana.
- **Large electricity users (data centers and the like) connecting to the grid**: power
  plants only, and the README says so.
- **Permits, zoning, environmental limits, live grid data, paid data.**
- **Hand-written loaders for other grid operators**: LBNL already covers the rest of the
  country.
- **Kafka**: there is one pipeline and one consumer, and nothing needs an ordered event
  history.
- **Login system**: a single-user demo; rate limiting and the spending cap are enough.
- **Next.js, Kubernetes.**
- **promptfoo**: a pytest file over a labelled CSV measures the same thing without another
  configuration language.
- **Vector search / RAG**: the data is already in tables with known columns, so plain SQL is
  the right tool.
- **Fuzzy matching while the program runs**: only offline, for suggesting groupings.

## Notes

**Get the hard-to-change decisions right now.** Five things are cheap now and painful to
change later: separate `iso` and `study_region` columns, the sources' own row IDs, one view
per dataset with `source` required, saving every query's ID and returned rows, and structured
claims from the start. Messy loading code, the allowed margins, and prompt wording can all be
fixed later.

**The model's small role is the design, not a gap.** SQL does the filtering, tested functions
do the analysis, code does the checking, and the renderer writes the text. What's left for
the model is turning a plain-language description of a site into query parameters, and
turning several function results into readable prose that is honest about uncertainty. The
README should say this before a reviewer asks.

**A known blind spot that's acceptable.** Test cases about substation names check that the
agent *uses* the cleaned-up name. They can't catch a wrong grouping, because the agent and
the expected answer both use the same grouping table. Whether the groupings are right is
covered by the name-cleaning unit tests and a one-time manual review. Test cases about
keeping the two datasets apart mostly pass automatically (the views and the required `source`
make mistakes hard). They're kept to make sure that stays true.

**Reporting the AI reviewer's accuracy** (when build step 6 arrives): give raw counts per
category plus one overall rate of bad answers it let through, with the number of samples
stated. Rates per category, with about 5 samples each, would be noise.

**Wording.** Earlier drafts called the hand-written expected-answer queries "oracle SQL".
That reads like Oracle Database, so the name was dropped. They are plain Postgres queries.
