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

Not built yet: the numbers, the agent, the checking, and the map app. See the
[product spec](docs/specs/product-spec.md).

## Requirements

- [Docker](https://www.docker.com/) (runs the Postgres database)
- [uv](https://docs.astral.sh/uv/) (installs Python and the project's dependencies)

## Start the database and run the tests

```bash
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

## Before the first model call: API key and spending cap

Nothing calls the model yet, but the guards for when something does are already in place.

1. **Set a monthly spending cap in the Anthropic console first.** This is required, not
   optional. It is the one limit that holds even if the code has a bug, so it must exist
   before any agent run.
2. **Put the API key in `.env`, never in a committed file.** Copy `.env.example` to `.env`
   and fill in `ANTHROPIC_API_KEY`. Git ignores `.env`, and CI scans every commit for
   anything that looks like a key and fails the build if it finds one.
3. **Per-assessment limits are enforced in code** (`interconnection_agent.budget`). One
   assessment may make at most `AGENT_MAX_TURNS` model calls (default 10) and use at most
   `AGENT_MAX_TOKENS_PER_ASSESSMENT` tokens in total (default 200,000). Each call may write
   at most `AGENT_MAX_OUTPUT_TOKENS_PER_CALL` tokens (default 16,000). Going over any of these
   stops the assessment with an error that names the limit. An answer the model could not
   finish is also an error, not a shorter answer passed along as if it were complete.
   A call's token count is only known once it returns, so the call that crosses the total
   is still paid for: the total can go over by at most one call, and then everything stops.

## Developer checks

The same checks CI runs on every push and pull request (see `.github/workflows/ci.yml`).
CI also scans the full git history for leaked keys, which needs no local step.

```bash
uv run ruff check           # lint
uv run ruff format --check  # formatting
uv run mypy                 # type check (strict)
uv run pytest               # tests (needs Postgres running)
```

## Layout

```
src/interconnection_agent/        # the application code
src/interconnection_agent/tests/  # fast tests for that code (no database)
tests/integration/                # tests against the real Postgres
tests/e2e/                        # whole-system tests (none yet)
data/                             # the saved source spreadsheets, and their credits
docker-compose.yml                # the local Postgres
.github/workflows/ci.yml          # CI: checks, tests, and the key scan
docs/                             # design decisions, plans, agent instructions
CONTEXT.md                        # what the domain words mean
```

Where tests go is explained in [`tests/README.md`](tests/README.md).

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
2. **Look up in a reviewed table** (`src/interconnection_agent/poi/aliases.csv`, in version
   control). Each tidied name maps to one official name, by exact match only. This is where
   real synonyms, typos ("Vota-South" → "Volta-South"), and different endings get grouped.
   A name with no entry gets `normalized_poi = NULL` and `poi_unmapped = true`. It's counted,
   never guessed.

Fuzzy matching is only used by an offline helper script
(`scripts/propose_poi_aliases.py`, using `rapidfuzz`) that suggests groupings for a person
to review. The running program can't import it, and the test `test_poi_offline_only.py`
fails if anyone tries.

**Measured coverage** (CAISO's waiting projects, report dated 07/24/2026): of 270 waiting
projects (76,287 MW), **2 projects totalling 1,100 MW, or 1.44% of the MW waiting, have no
match.** Both are because their substation is only proposed and doesn't exist yet, so there
is no connection history there anyway. The target was under 2% of the MW waiting. To
reproduce the number:

```bash
# Needs Postgres running (see above); prints the coverage line as it loads.
PYTHONPATH=src uv run python -m interconnection_agent.cli ingest data/publicqueuereport.xlsx
```

The reviewed groupings are also compared with the substation names in LBNL's dataset for the
projects that appear in both. Any disagreement is reported for review by
`tests/integration/test_poi_lbnl_crosscheck.py`.

## Data and credits

The `data/` folder holds saved copies of the public datasets this project loads: CAISO's
Public Queue Report and LBNL's "Queued Up" file. They're used for educational and research
purposes and aren't covered by this repository's software license. Each source's credit and
terms are in [`data/README.md`](data/README.md). Neither CAISO, LBNL, nor GridTracker
endorses this project.
