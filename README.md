# interconnection-agent

Before anyone builds a solar farm, wind farm, or large battery, they have to ask the local
grid operator for permission to connect it to the grid. Every operator keeps a public
waiting list of these requests, called the **interconnection queue**. The queue says a lot
about how risky a site is: how many projects are already waiting to connect at the same
substation, how long similar projects took to get connected, and how many gave up along the
way.

This project is an AI agent that reads that public queue data and writes a short risk
assessment for a proposed site. What makes it different: **every number in the assessment
is linked to the exact rows of source data it came from, and ordinary code checks the number
before anyone reads it.** If a number can't be reproduced from the data, it doesn't appear.
Anything the code can't check is labelled as unchecked.

The main idea is *checked answers, not just automated ones*. Plenty of tools can get a
model to write a fluent report. The point here is that you can trace every figure back to
the data and confirm it yourself.

> **Scope:** power plants connecting to the grid only. Not large electricity users like
> data centers, which go through a different process.

More detail:

- [`CONTEXT.md`](CONTEXT.md): what the domain words mean (substation, queue-entry year, and
  so on).
- [`docs/adr/`](docs/adr/): short write-ups of the main design decisions and why they were
  made.
- [`docs/specs/product-spec.md`](docs/specs/product-spec.md): what the product does, as a
  short list of behaviours.

## Where it stands

Built so far:

- **Loading the data.** California's grid operator (CAISO) publishes its queue as a messy
  spreadsheet: three tabs, headers on row 4, up to three fuel types per row, and substation
  names typed by hand. A hand-written loader reads all three tabs into one database table.
  A second loader reads Berkeley Lab's national queue dataset (LBNL), which covers the whole
  country.
- **Grouping substation names.** The same substation is spelled several ways in the CAISO
  file. Spellings are grouped through a table a person has reviewed (see below), and any
  name that isn't in the table is flagged, never guessed.
- **Cross-checking the loader.** CAISO projects appear in both datasets. Tests work out the
  share of projects that dropped out and the share that got connected, once from CAISO's
  own file and once from LBNL's copy, and compare both with a published California Public
  Advocates report. If the loader breaks, the numbers drift apart and the test fails.
- **Spending and secret guards.** Limits on how much one assessment can spend on the model,
  and a CI check that fails if an API key is ever committed. These are in place before
  anything calls the model.

- **Places, positions, and what's around them** (ticket "Load and organise the data"): one call,
  `load_all`, loads both CAISO queue reports (including the 2023 batch), how far each project
  got, estimated dates where a real one is missing, where each project connects (98.9% of
  projects; projects on a line count at both ends), map positions from OpenStreetMap (69% of
  waiting MW; the rest falls back to its county), the bottlenecks each place sits behind with
  the cost to add room, and planned grid upgrades. 145 places now have 5 or more past outcomes
  to learn from, up from 15. Anything the reviewed tables don't recognise is reported.

- **The numbers** (ticket "Chances, waits, and who's ahead"): the chance of being built
  within N years and the typical wait for projects like yours, realistic MW ahead at each
  substation, and a check of past predictions against what happened.

- **The checked assessment** (ticket "The agent writes a checked assessment"): the model looks
  things up and writes an assessment made only of Factual Claims and Judgements, following
  the writing skill (`backend/src/interconnection_agent/skills/writing-an-assessment/SKILL.md`).
  Code checks every number before it's shown (see "What the checking proves" below). A
  person can leave projects out or pick a narrower or broader comparison group (the numbers
  are worked out and checked again), approve, reject or rewrite each Judgement, and
  finalise once every Judgement is decided. Every change is logged. A plain request ("ignore projects stuck since 2019") becomes a proposed
  change that applies only when a person confirms it.

- **The map app, Headway** (ticket "The map app"): a website (`frontend/`, Next.js and Leaflet)
  over a small API (`interconnection_agent.api`). A landing page explains the queue before
  showing any substation. The map shows California's counties from US Census boundaries,
  every substation with projects waiting coloured by realistic MW ahead, planned substations
  as hollow rings, and substations without an exact position as "+N" badges on their county,
  never as guessed dots. A substation page answers three plain questions first (will it get
  built, how long does it take, how crowded is it), with charts, the projects ahead, upgrades
  and costs, and the groups of past projects it was compared with, in tabs. Every number opens the rows it came from.
  **Ask** answers questions with checked facts, held until you add them to the write-up, and
  says plainly when the data can't answer something; changes to what's counted are shown
  first and apply only once confirmed. **Write-up** is where a person agrees with, disagrees
  with or rewords each Judgement, then finalises.

Not built yet: saving and sharing assessments, and the public site. See the
[product spec](docs/specs/product-spec.md).

## What the checking proves, and what it doesn't

The model never writes the text a reader sees. It submits claims: a sentence with a slot for
each number, and for each number the lookup it came from, how it was worked out, and the
rows it used. Every lookup is logged with every row it returned. Before anything is shown,
plain code (`interconnection_agent.assessment.check`) confirms, for every number:

- it reproduces from the data, within a margin written down per unit (MW to the nearest 10
  or 5%, years to one decimal place, percentages to the whole point, counts exactly);
- it uses exactly the rows its lookup returned, so a number built from a convenient few of
  them fails even when the arithmetic is right;
- its rows are rows of the dataset it names, and its lookup is in the log;
- the sentence holds no number outside its slots.

A claim that fails isn't shown, and leaving projects out later never brings it back. A
Judgement is never shown as checked, and can't state a number of its own. Two things code
can't catch, so the writing skill rules them out: numbers written as words ("half"), and
interpretation slipped into a Factual Claim's sentence. The tests feed the checker correct claims and deliberately broken copies
(`backend/tests/integration/test_number_check.py`); every broken one is caught.

What it can't prove is that the lookup was the *right* one: the wrong substation or a missing
filter gives numbers that check out perfectly about the wrong thing. Answer-key questions
with hand-written SQL answers (`backend/tests/e2e/test_answer_key.py`) check that the agent picks the
right rows. They call the real model, so they run only when `ANTHROPIC_API_KEY` is set. What
neither can judge is whether past projects are a fair comparison for this one: that's what
the Judgements, and the person deciding on them, are for.

## Requirements

- [Docker](https://www.docker.com/) (runs the Postgres database)
- [uv](https://docs.astral.sh/uv/) (installs Python and the project's dependencies)

## Start the database and run the tests

The Python code, its tests and the database setup live in `backend/`; run these commands there.

```bash
cd backend

# 1. Start Postgres (on port 5433 of your machine; see below).
docker compose up -d

# 2. Install dependencies into a local virtual environment.
uv sync

# 3. Run the tests against that database.
uv run pytest
```

When you're done:

```bash
docker compose down          # stop Postgres, keep its data
docker compose down -v       # stop Postgres and delete its data
```

### Database settings

The code reads the database address from the `DATABASE_URL` environment variable. If it
isn't set, it uses the local Docker database, so the steps above need no setup.

Docker exposes Postgres on **port 5433** of your machine (not the usual 5432), so it doesn't
clash with a Postgres you may already have installed. CI uses the same port, so the default
address works the same way there.

## Run the website

```bash
# 1. In backend/, load the data into the database and keep it (about 30 seconds).
cd backend
uv run python -m interconnection_agent.cli load

# 2. Start the API on port 8000. Written assessments use Claude if ANTHROPIC_API_KEY is
#    set (see below); everything else works without it.
uv run python -m interconnection_agent.api

# 3. In another terminal, start the website, then open http://localhost:3000.
cd frontend && npm install && npm run dev
```

The website sends `/api` requests to `http://127.0.0.1:8000`; set `HEADWAY_API` to point it
elsewhere. The first visit to the map takes about 15 seconds while every substation's
realistic MW ahead is worked out; after that it's kept until the API restarts.

## Before the first model call: API key and spending cap

The agent calls the model, and these guards apply to every call it makes.

1. **Set a monthly spending cap in the Anthropic console first.** This is required, not
   optional. It is the one limit that holds even if the code has a bug, so it must exist
   before any agent run.
2. **Put the API key in `backend/.env`, never in a committed file.** Copy `backend/.env.example` to `backend/.env`
   and fill in `ANTHROPIC_API_KEY`. Git ignores `.env`, and CI scans every commit for
   anything that looks like a key and fails the build if it finds one.
3. **Per-assessment limits are enforced in code** (`interconnection_agent.budget`). One
   assessment, writing it and answering questions about it, may make at most
   `AGENT_MAX_TURNS` model calls (default 10) and use at most
   `AGENT_MAX_TOKENS_PER_ASSESSMENT` tokens in total (default 200,000). Each call may write
   at most `AGENT_MAX_OUTPUT_TOKENS_PER_CALL` tokens (default 16,000). Going over any of these
   stops the assessment with an error that names the limit. An answer the model could not
   finish is also an error, not a shorter answer passed along as if it were complete.
   A call's token count is only known once it returns, so the call that crosses the total
   is still paid for: the total can go over by at most one call, and then everything stops.
   Tokens read from or written to the prompt cache count too.
4. **The model is a setting.** `ANTHROPIC_MODEL` is `claude-sonnet-5-5` by default, or
   `claude-haiku-5-5` or `claude-opus-5-5`. Each call caches the conversation so far, since
   every turn sends it again. On Sonnet and Opus, a request declined on safety grounds is
   retried on a fallback model; Haiku 5.5 has none.
5. **The public site has limits of its own** (`interconnection_agent.spending` and
   `interconnection_agent.api.write_ups`):
   - **A monthly spend limit**, `SPEND_LIMIT_PER_MONTH_USD` (default $10). Every model call,
     on any model, is priced from the tokens it used and counted. Once the month's total
     reaches the limit, new write-ups and questions are refused until the 1st, California
     time. A call already under way can take the total over by at most that one call.
   - **Write-ups per visitor per day**, `WRITE_UPS_PER_VISITOR_PER_DAY` (default 3), and
     **per day for the whole site**, `WRITE_UPS_PER_DAY` (default 20). A day ends at
     midnight, California time. Setting either to 0 turns write-ups off.
   - A visitor is known by the address the website's host passes on, kept only as a keyed
     hash for two days. Someone calling the API directly can get round the per-visitor
     limit, but not the daily or monthly ones.

## Deploy

The API runs on [Railway](https://railway.com) and the website on [Vercel](https://vercel.com).
Each deploys from its own folder of this repository.

**The API, on Railway**

1. Create a project with a **Postgres** database, then add a service from this GitHub
   repository.
2. In the service's settings (Railway no longer reads settings from a file in the repository
   for new services, so these are set in its dashboard):
   - **Source:** root directory `/backend`, and turn on **Wait for CI** so only changes that
     pass the checks are deployed.
   - **Build:** the builder is the Dockerfile (`backend/Dockerfile`, found on its own once the
     root directory is set). Watch paths: `/backend/**`, so only changes to the API redeploy.
   - **Deploy:** pre-deploy command `python -m interconnection_agent.cli load`, and restart
     on failure.
3. Give the service these variables:
   - `DATABASE_URL`: `${{Postgres.DATABASE_URL}}`, which points at the project's database.
   - `ANTHROPIC_API_KEY`: only if the site should write assessments. Set the spending cap
     in the Anthropic console first (see above). Without a key, everything else works.
   - Optionally, `ANTHROPIC_MODEL`, the site's limits, and the `AGENT_MAX_*` limits, all
     listed in `.env.example`. Changing a variable redeploys the service.
4. Under networking, generate a public domain for the service.

Before each deploy goes live, Railway loads the committed data into the database
(`cli load`, about 30 seconds). Loading again gives the same rows, so the data always
matches the deployed code. Only changes under `backend/` start a new deploy.

**The website, on Vercel**

1. Import this repository and set the root directory to `frontend`.
2. Set `HEADWAY_API` to the API's Railway address, for example
   `https://headway-api.up.railway.app`, with no slash at the end.

The website passes `/api` requests on to that address, so the browser only ever talks to the
website. Writing an assessment takes a minute or two, longer than Vercel waits for one
request, so the page starts it and then checks back every two seconds until it's done.

## Developer checks

The same checks CI runs on every push and pull request (see `.github/workflows/ci.yml`).
CI also scans the full git history for leaked keys, which needs no local step.

```bash
cd backend
uv run ruff check           # lint
uv run ruff format --check  # formatting
uv run mypy                 # type check (strict)
uv run pytest               # tests (needs Postgres running)

cd ../frontend
npm run typecheck           # the website's types
```

The browser tests (`backend/tests/e2e/test_map_app.py`) run the website, the API and the database
together in Chromium, with a scripted stand-in for the model. They need the data loaded
(`cli load`), `npm install` in `frontend/` and `uv run playwright install chromium`, and are
skipped otherwise.

## Layout

```
backend/                                  # the API, the numbers, the checking (Python)
backend/src/interconnection_agent/        # the application code
backend/src/interconnection_agent/api/    # the API the website reads (FastAPI)
backend/src/interconnection_agent/tests/  # fast tests for that code (no database)
backend/tests/integration/                # tests against the real Postgres
backend/tests/e2e/                        # the website in a browser, and tests of the real model
backend/data/                             # the saved source spreadsheets, and their credits
backend/docker-compose.yml                # the local Postgres
backend/Dockerfile                        # how Railway builds and runs the API
frontend/                                 # the website, Headway (Next.js and Leaflet)
.github/workflows/ci.yml                  # CI: checks, tests, and the key scan
docs/                                     # design decisions, plans, agent instructions
CONTEXT.md                                # what the domain words mean
```

Where tests go is explained in [`backend/tests/README.md`](backend/tests/README.md).

## Grouping substation names

In CAISO's file, the substation (the "point of interconnection", or POI) is typed by hand.
The same place appears as "Whirlwind Substation 230kV", "WHIRLWIND Substation 230 kV", and
"Whirlwind Sub 230kV bus". To count projects per substation, those spellings have to be
grouped. That happens in two steps, and neither involves guessing, because a guessed
grouping could quietly change which rows a checked number is built from:

1. **Tidy up** (`interconnection_agent.poi.normalize`). This only removes differences that
   don't change meaning: odd characters, upper versus lower case, extra spaces, `230kV`
   versus `230 kV`, and spacing around hyphens. It keeps words like "Substation", "Line",
   and "Bus", and never merges voltage levels. A 230 kV bus and a 500 kV bus at the same
   site are different connection points.
2. **Look up in a reviewed table** (`backend/src/interconnection_agent/poi/aliases.csv`, in version
   control). Each tidied name maps to one official name, by exact match only. This is where
   real synonyms, typos ("Vota-South" → "Volta-South"), and different endings get grouped.
   A name with no entry gets `normalized_poi = NULL` and `poi_unmapped = true`. It's counted,
   never guessed.

Fuzzy matching is only used by an offline helper script
(`backend/scripts/propose_poi_aliases.py`, using `rapidfuzz`) that suggests groupings for a person
to review. The running program can't import it, and the test `test_poi_offline_only.py`
fails if anyone tries.

**Measured coverage** (CAISO's waiting projects, report dated 07/24/2026): of 270 waiting
projects (76,287 MW), **2 projects totalling 1,100 MW, or 1.44% of the MW waiting, have no
match.** Both are because their substation is only proposed and doesn't exist yet, so there
is no connection history there anyway. The target was under 2% of the MW waiting. To
reproduce the number:

```bash
# In backend/, with Postgres running (see above); prints the coverage line as it loads.
PYTHONPATH=src uv run python -m interconnection_agent.cli ingest data/publicqueuereport.xlsx
```

The reviewed groupings are also compared with the substation names in LBNL's dataset for the
projects that appear in both. Any disagreement is reported for review by
`backend/tests/integration/test_poi_lbnl_crosscheck.py`.

## Data and credits

The `backend/data/` folder holds saved copies of the public datasets this project loads: CAISO's
Public Queue Report and LBNL's "Queued Up" file. They're used for educational and research
purposes and aren't covered by this repository's software license. Each source's credit and
terms are in [`backend/data/README.md`](backend/data/README.md). County and state outlines on the map come
from the US Census Bureau's cartographic boundary files (2023, public domain). Substation
positions come from
OpenStreetMap: © OpenStreetMap contributors, under the
[Open Database License](https://www.openstreetmap.org/copyright). Neither CAISO, LBNL, nor GridTracker
endorses this project.
