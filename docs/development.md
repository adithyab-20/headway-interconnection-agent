# Development and deployment

[← Headway](../README.md)

## Requirements

- [Docker](https://www.docker.com/) (runs the Postgres database)
- [uv](https://docs.astral.sh/uv/) (installs Python and the project's dependencies)
- Node.js 22 and npm (runs the frontend)

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
# From the repository root:
cd frontend
npm ci
npm run dev
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

Where tests go is explained in [`backend/tests/README.md`](../backend/tests/README.md).

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
purposes and remain subject to their source terms. Each source's credit and
terms are in [`backend/data/README.md`](../backend/data/README.md). County and state outlines on the map come
from the US Census Bureau's cartographic boundary files (2023, public domain). Substation
positions come from
OpenStreetMap: © OpenStreetMap contributors, under the
[Open Database License](https://www.openstreetmap.org/copyright). Neither CAISO, LBNL, nor GridTracker
endorses this project.
