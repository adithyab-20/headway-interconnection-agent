# Interconnection Due-Diligence Agent: Build Plan

This plan is meant to stand on its own, so assume no other context. The decisions below were
made on purpose. Follow them as written, and ask before changing the design.

## 1. What this is

An AI agent that judges how risky it will be to connect a proposed solar, wind, or battery
site to the grid, using public interconnection-queue data (each grid operator's public list
of projects waiting to connect). **Every number it states is linked to specific source rows
and checked by code.** The main idea is *checked answers, not just automated ones*. What sets
it apart is not that a model wrote a report, but that every number in the report can be shown
to come from the data it cites.

**Tools:** Python, FastAPI, Postgres, LangGraph, the Anthropic Messages API, Celery and
Redis, a React/TypeScript dashboard, pytest, Docker Compose, and GitHub Actions for CI.

**No document search.** The data is already in tables with known columns, so the agent gets
data by calling SQL queries with parameters, never by searching text (no vector search, no
"RAG"). Fuzzy name matching (`pg_trgm` or `rapidfuzz`) is used **only offline, to build the
substation-name table**: it suggests possible groupings of substation spellings for a person
to review. It is NEVER used while the program answers a question. At that point, rows are
matched exactly on `normalized_poi` using the reviewed, checked-in table. If grouping were
guessed at question time, "which rows belong to this substation" could change from run to
run. That would break the all-rows check (section 5) and the broken-claim tests (section 6),
which both depend on a fixed answer.

## 2. Data sources (saved copies, kept in the repo or pinned to a version)

1. **CAISO Public Queue Report** (`publicqueuereport.xlsx`): California's grid operator's
   own spreadsheet. Three tabs: waiting (~271 projects), completed (~248), and withdrawn
   (~1,760). Headers on row 4. Up to three fuel-type/MW column pairs per row. A substation
   column typed by hand that needs cleaning up. **Loaded by a hand-written loader**, which is
   the main engineering showcase. The completed tab gives real wait times (median about 6.2
   years).
2. **LBNL "Queued Up"** (`LBNL_Ix_Queue_Data_File_thru2025.xlsx`): Berkeley Lab's
   already-cleaned dataset covering the whole country (all 9 regions, 38,201 rows), with a
   codebook explaining each column. Loaded to give **national coverage**, and used as an
   **independent check** on figures calculated from CAISO's own file.
3. **California Public Advocates report (PDF)**: independent published CAISO figures (about
   71% withdrawn and about 20% completed). Used only as reference numbers in the loader's
   tests, never loaded as data the agent can query.

Cross-check: after loading, automatic tests compare figures calculated from CAISO's own file
with LBNL's copy of the CAISO projects and with the Public Advocates figures, each within a
stated margin.

## 3. Database decisions (fixed)

- Store location in two columns: **`iso`** (the grid operator) and **`study_region`** (the
  planning area inside it). Never one `region` column.
- LBNL's "West" and "Southeast" have no grid operator. They get `iso = NULL` plus a
  `non_iso_entity` column for the local utility area. Never `iso = 'West'`.
- **One Postgres view per dataset**: `caiso_projects` and `lbnl_projects`. All analysis
  reads a view, so counting a project twice (it can appear in both datasets) can't happen.
- Every analysis function takes a **required `source` argument with no default**.
- **Row IDs are the sources' own IDs**: CAISO rows by CAISO queue position (for example
  `CAISO-0123`), LBNL rows by LBNL's own project ID. Never auto-numbered IDs. The answer-key
  test cases store these IDs, and they must stay valid when the data is loaded again.
- The cleaned-up substation name goes in `normalized_poi`, and the original text is kept in
  `raw_poi`. (Use exactly these column names everywhere.)
- **How substation names get grouped, and when to stop working on it:** rapidfuzz or
  pg_trgm suggest possible groups offline → a person reviews them into a **checked-in table**
  (versioned and unit-tested) → the loader applies it. A row with no reviewed match gets
  `normalized_poi = NULL` and `poi_unmapped = true`, never a guessed match. **Stop when
  unmatched rows cover less than 2% of the MW waiting in the queue, or after one day of
  work, whichever comes first.** Report the coverage number in the README. Analysis
  functions must report unmatched rows in their results (an honest "N rows left out, X MW")
  rather than silently dropping them.
- **Checking the groupings:** LBNL's `poi_name` covers the same CAISO projects. A test
  compares the reviewed groupings with LBNL's names for the projects in both datasets and
  reports any disagreement for review.

## 4. How the agent works (LangGraph)

Steps, roughly: Plan → Retrieve (run SQL queries) → Analyze (run the tested analysis
functions) → Assess (write claims) → Check (the number checker) → Render (build the text).

- **Retrieve** calls SQL queries with parameters: substation lookup, county or planning-area
  filter, grid operator plus status plus technology filter, and date or size filters. Each
  query requires `source`. **All filtering happens in SQL.** If the agent wants "solar
  projects at this substation", it calls the query with the solar filter. It never takes a
  broader result and picks rows out of it in its head. Every query result gets a
  `tool_call_id`, and the full list of row IDs it returned is saved in the query log.
- **Analyze**: the analysis layer. **The four named analysis functions are the product:**
  - `get_poi_context(source, poi)`: how many projects at a substation are waiting, finished,
    and withdrawn.
  - `get_historical_timeline(source, filters)`: how long finished projects waited before
    starting operation. **Always returned with the warning** that only finished projects can
    be measured, so the number looks better than reality.
  - `get_withdrawal_rate(source, filters)`: **worked out per queue-entry year**, because
    recent projects haven't had time to drop out yet, and a single rate over all years comes
    out too low.
  - `get_local_saturation(source, poi)`: MW waiting at the substation compared with MW
    connected there before. This needs CAISO's own file, which is why the hand-written
    loader matters.
  - Plus general statistics (median, percentiles). All of these are **ordinary, separately
    tested functions**. The model calls them and quotes their results exactly. It never
    recalculates any of these from raw rows. These four functions hold the expert judgement.
    Without them, this would just be a generic SQL agent with citations.
- **Assess** returns **structured claims, not prose**. Each number names the `tool_call_id`
  it came from:

```json
{
  "claims": [
    {
      "text": "Active projects at MOSS LANDING total 2,450 MW.",
      "values": [
        {
          "value": 2450,
          "unit": "MW",
          "derivation": "sum",
          "source_row_ids": ["CAISO-0012", "CAISO-0018", "CAISO-0023"],
          "tool_call_id": "tc_004",
          "source": "caiso_raw"
        }
      ]
    }
  ]
}
```

- `derivation` (how the number was worked out) must be one of: `direct | sum | count |
  median | ratio`. There is one checking function for each. For `median` and the four
  analysis functions' outputs, checking means confirming the claim quotes exactly what the
  tested function returned, not recalculating it.
- `source` must be one of: `caiso_raw | lbnl`. Use exactly these strings everywhere: in the
  claim format, the broken-claim tests, the views, and the docs.
- **Render** writes text only from claims that passed the check. The text comes after the
  check and is never parsed back.

## 5. Checks that run on every assessment

- **The number check (code only, no model):** for each number, look up its
  `source_row_ids` in the database, apply the checker for its `derivation`, and compare
  within a **margin set per unit** (written down and versioned). Because claims are
  structured, this is a database lookup, never parsing text.
- **The all-rows check:** for each number, compare the rows it cites with the rows its
  `tool_call_id` actually returned (from the saved query log). For `sum`, `count`, `median`,
  and `ratio` they must be **exactly the same rows**. For `direct`, the cited row must be
  one of them. This makes picking convenient rows impossible. An agent that cites 2 of 3
  returned rows and adds them up correctly still FAILS. It costs one set comparison per
  number.
- **The AI reviewer:** a second model grades only the wording-based parts of an assessment:
  how uncertainty is handled, whether a cause is overstated, whether the evidence supports
  the statement, and whether recommendations hang together. Each is a separate pass or fail,
  and the reviewer may answer "unknown". The reviewer is **measured, not trained**: its
  agreement with about 30 human-graded samples is measured and reported as a number. A
  smaller, cheaper model is fine if it measures well. The examples given to the reviewer in
  its prompt must not overlap with the samples it is measured on.
- **Human review:** the quality of the reasoning can't be fully checked automatically. This
  is stated as an honest limit.

**What the number check can't prove (say this in the README):** it proves the arithmetic,
where each number came from, and that each claim used every row its query returned. It does
NOT prove the query itself was the *right* one (wrong substation, missing filter, wrong
tool). That gap is covered offline by the row-selection test (section 6, Test 2). The two
work together; neither replaces the other.

## 6. Offline tests of the agent (separate from the checks above)

The checks in section 5 ask "can I trust this one report?" The offline tests ask "across
known questions, how reliable is the agent, and did a change make it worse?" There are three
kinds, kept in separate folders:

```
evals/
├── answer_key/         # ~30 answer-key cases → Tests 1 and 2 (test the AGENT)
│   ├── cases/*.yaml
│   └── sql/*.sql       # hand-written expected-answer queries, open to inspection
├── reviewer_grades/    # ~30 human-graded samples → Test 3 (tests the AI REVIEWER)
│   └── labels.json
├── broken_claims/      # generated correct and broken claims (tests the NUMBER CHECKER)
├── graders/            # arithmetic.py, provenance.py, retrieval.py, judge.py
└── run_evals.py        # pytest-based runner
```

### Test 1: are the numbers right? (graded by code)

Run the agent on an answer-key case → take its structured claims → work out the expected
numbers independently, from that case's **hand-written expected-answer queries** or
pre-computed answers → compare value, unit, derivation, and row IDs. Measures: share of
claims that pass, claims with no support, arithmetic errors, missing citations, wrong units,
and share of whole reports that pass. The grader must NOT call the number checker from
section 5. It must work out the answers on its own.

**Why the expected answers must be independent (the reason these queries exist).** The
expected-answer queries are plain Postgres, written by hand from what each question means.
They never call the agent's own analysis or query functions. If the expected value came from
the code being tested, a bug would show up on both sides and the test would pass while both
were wrong, which only proves a function agrees with itself. This duplication is on purpose.
Avoiding repetition is the wrong instinct here. Don't "fix" it later.

### Test 2: did it pick the right rows? (graded by code)

Compare the set of row IDs the agent cited with the expected set. Measures: exact match,
precision (how many cited rows were right), and recall (how many right rows were cited). Only
for questions where the right rows can be pinned down exactly (substation, county, status,
technology, date, and size filters). NOT for vague "similar projects" questions. Say so.

### Test 3: how good is the AI reviewer? (measured against human grades)

Run the AI reviewer on the ~30 human-graded samples. The grades cover: well supported,
overstated cause, uncertainty handled well, overconfident, contradicts itself, and not enough
evidence. Report overall agreement and **one overall rate of bad answers the reviewer let
through**, with the number of samples stated. Bad reasoning graded as PASS is the dangerous
mistake, so never report plain accuracy alone. These samples are separate from the
answer-key cases. Don't mix them up.

**Report raw counts per category, not rates.** Six categories over ~30 samples is about 5
each, so one changed grade moves a per-category "rate" by 20 points. A table of raw counts
plus one overall rate is the honest way to show it. Per-category percentages at this sample
size just invite a reviewer to find the hole for you.

### Broken-claim tests (unit tests for the number checker)

Generate correct claims plus deliberately broken copies, and measure how often the number
checker lets a broken one through and how often it rejects a correct one.

- Must PASS: the same decimal written differently, rounding within the margin, row IDs in a
  different order, a correct direct quote.
- Must FAIL: a value outside the margin; a missing or extra source row; **citing only some
  of the returned rows while the arithmetic on them is right** (the case the all-rows check
  exists for); MW and GW mixed up without converting; the wrong derivation label (says
  `sum`, is a `ratio`); an LBNL row cited as `source="caiso_raw"`; CAISO's and LBNL's copies
  of the same project mixed together; a withdrawn project in a claim about waiting projects;
  a number citing no rows; a `tool_call_id` that isn't in the query log.

Describe these in the README as unit tests of a piece of code that always gives the same
answer.

### How to build the answer-key cases (follow this method; don't hand-inspect 38,000 rows)

1. Freeze the dataset copies, the loader version, and the substation-table version, and
   record them in each case.
2. Explore the database with SQL to find good real examples: substations with 3–15
   projects, mixes of waiting and withdrawn, projects with several technologies, spelling
   variants, substations with one project, and filters guaranteed to return nothing.
3. Write the question. Keep a deliberate mix of very explicit questions ("projects whose
   cleaned substation name is exactly X, status Active") and natural ones that still have
   one right answer ("How crowded is the queue at Moss Landing?"), which force the agent to
   interpret correctly. Rewrite any unclear question until two people who know the field
   would agree on the rows.
4. Write the **expected-answer query** by hand (never using the agent's own query
   functions; a shared bug would give a false PASS). Save the row IDs and worked-out values
   (count, sum, and so on) in the case's YAML file, and commit the SQL file.
5. **Check each expected-answer query by hand once:** does the SQL match the question, are
   the rows really relevant, are there traps with empty values or naming, could the question
   reasonably mean something else?
6. Target mix (~30 in total): 5 exact substation, 4 substation spelling, 3 county or planning
   area, 3 technology plus status, 2 date or size, 3 combined filters, 2 empty results, 2
   keeping the two datasets apart, and **6 analysis cases**: the per-year dropout rate, the
   wait time with its warning, the crowding comparison, a CAISO-against-LBNL comparison, and
   one where the warning itself is the expected answer. Analysis cases grade both the numbers
   (against expected-answer queries that redo the per-year and crowding logic independently)
   and whether the required warnings are present. Without these six, the tests would
   certify a generic SQL agent, not this product. Include empty-result cases on purpose, to
   check that the agent says "no matching evidence" instead of widening the question or
   inventing an answer.
7. Build in three rounds: 10 simple → 10 with combined filters → 10 tricky cases (spelling
   variants, similar substation names, empty values, solar-plus-battery hybrids and other
   multi-fuel rows, projects in both datasets, LBNL's no-operator areas, withdrawn versus
   waiting confusion).

A known blind spot to mention in the README: substation-spelling cases check that the agent
*uses* the cleaned-up name. They can't catch a wrong grouping, because the agent and the
expected answer both use the same table. Whether the groupings are right is covered by the
name-cleaning unit tests and a one-time manual check. Cases about keeping the two datasets
apart mostly pass automatically (the views and the required `source` make mistakes hard).
Keep them anyway, to make sure that stays true.

### When the tests run in CI

- Every pull request: the 30 answer-key cases once each, graded by code only; the
  broken-claim tests; and the loader cross-checks.
- Nightly or before a release: the 30 cases three times each (report how often the first
  try passes and how often all three pass; consistency matters for a product about trust,
  but don't read too much into small gaps with 30 cases), plus an AI reviewer run. **Off by
  default.** That's about 90 agent runs plus a reviewer pass each night, the biggest regular
  cost in the project. Turn it on deliberately once the spending cap in section 8 is set and
  confirmed, not as part of the first CI setup.
- Test environment: the Docker Compose Postgres, loaded from the saved spreadsheets by the
  real loader. No separate snapshot setup.
- Failed real-world runs get turned into new test cases. (One sentence in the README is
  enough; don't build tooling for it now.)

## 7. Build order (in priority order; don't polish later steps before earlier ones are done)

1. **Step 1, load the data:** the hand-written CAISO loader (three tabs, headers on row 4,
   multi-fuel columns); the substation-name table (offline suggestions → human review →
   checked in; unmatched rows flagged; stop at under 2% of waiting MW or one day; compare
   with LBNL's `poi_name`); the LBNL loader following its codebook; the sources' own row IDs;
   and cross-checks against LBNL and Public Advocates.
2. **Step 2, database and data access:** tables, the `iso`/`study_region` split, the
   no-operator areas, one view per dataset, and SQL query functions that require `source`
   and save a `tool_call_id` plus the returned rows to the query log.
3. **Step 3, the agent's skeleton and the analysis functions:** the LangGraph graph, the SQL
   queries, then the **four analysis functions** (`get_poi_context`,
   `get_historical_timeline`, `get_withdrawal_rate`, `get_local_saturation`), unit-tested
   first. These working, with their sources attached, are the core result. Plus general
   statistics, the Anthropic API calls, a Celery task wrapper, and minimal FastAPI
   endpoints.
4. **Step 4, structured claims and the number check:** the claim format (including
   `tool_call_id` and the `source` list), the derivation list, one checker per derivation,
   the all-rows check against the query log, the margin table, and building text from
   checked claims.
5. **Step 5, answer-key tests and broken-claim tests:** the test runner, graders, and first
   10 answer-key cases; wire them into CI; grow to 30. (The most valuable step: this is
   where the project earns its credibility.)
6. **Step 6, the AI reviewer and measuring it:** only once the agent's written output is
   stable. A grading guide with separate dimensions and "unknown" allowed, then hand-grade
   ~30 samples and measure agreement.
7. **Step 7, dashboard and monitoring:** a React/TypeScript report page showing each claim
   with its check result, its cited rows (click through to the source data), and the
   measured AI-reviewer agreement number. A page summarising test results. **Monitoring,
   small but real:** structured JSON logs throughout; measurements saved for each assessment
   (time taken, token cost, share of numbers that passed, AI reviewer results, claims per
   report, rows left out as unmatched); LangGraph run logs saved and viewable; and a simple
   metrics panel in the dashboard. No Prometheus or Grafana unless there's time.

## 8. Secrets and cost

This is a one-person project on a personal API account. Both of these are cheap to set up
and expensive to discover late.

- **Secrets:** the API key lives in `.env`, which is never committed. `.env.example` is
  checked in with blank values. CI scans the whole git history for anything that looks like
  a key.
- **Spending cap:** set a hard monthly cap in the Anthropic console *before* the first agent
  run. It's the backstop that makes every other limit a convenience rather than the only
  protection.
- **Limits per assessment:** a maximum number of tokens and of model calls per assessment,
  enforced in code. An agent stuck in a loop is a bill, not just a bug.
- **CI cost:** the pull-request tests (30 cases once each, graded by code) are the
  affordable level. The nightly three-times run plus AI reviewer is off by default; see
  section 6.
- **If the demo is on the public internet:** limit requests per IP address using Redis, and
  add a switch that serves saved answers instead of calling the model. A login system is
  deliberately left out (it's a single-user demo, and adding one would show configuration
  rather than engineering).

## 9. What the README must say honestly

- The number check proves arithmetic, where numbers came from, and that each claim used
  every row its query returned. It doesn't prove the query was the right one. The
  row-selection test covers the part of that gap that can be tested exactly, offline. The
  two work together; neither replaces the other.
- Wait times only count projects that finished, so they look better than reality. Dropout
  rates are worked out per queue-entry year, because a single rate over all years comes out
  too low. The analysis functions add these warnings themselves; the model doesn't decide
  whether to mention them.
- Substation-name coverage: X% of waiting MW matched. Unmatched rows are flagged and left out
  openly, never guessed.
- The AI reviewer was measured against N human grades: X% agreement, and it let bad answers
  through Y% of the time. Measured, not trained.
- 30 answer-key cases guide development and catch things getting worse. They don't prove the
  agent is always right.
- The row-selection test only covers questions with one exact right set of rows. Questions
  about "similar projects" aren't tested automatically.
- The quality of the reasoning ultimately needs a person to review it.

### Why an agent and not a script: say this directly

This design deliberately keeps the model's job small. SQL does the filtering, tested
functions do the analysis, code does the checking, and the renderer builds the text from
checked claims. A reviewer will notice and ask what's left for the model. Answer first, in
these terms:

> The model turns a plain-language description of a site into query parameters, and
> combines several function results into readable prose that's honest about uncertainty. It
> does **not** pick rows, calculate statistics, or decide what counts as checked. Those are
> code, because they're the parts that must be right. LangGraph earns its place through the
> check that runs on every assessment and through steps that can each be tested on their
> own, not through clever routing. With this few tools, routing would be trivial, and
> claiming otherwise would be overselling it.

The model's small role is a *result* of the focus on checking, not a weakness in it. Put
that way, it's the strongest part of the design. Left unexplained, it's the first question
that goes badly.
