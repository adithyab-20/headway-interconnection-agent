# Tests

Where tests go in this repo:

- **Fast tests** live next to the code they test, in that component's own `tests/` folder
  (`src/<component>/tests/test_<module>.py`, for example
  `src/interconnection_agent/tests/test_db.py`). They must be quick and self-contained: no
  database and no network.
- **Database tests** live under `tests/integration/`, named `test_*.py`. They run against
  real infrastructure, mainly the Docker Compose Postgres (run `docker compose up -d`
  first). The database is never faked, because guarantees like "nothing is counted twice"
  are enforced by the database itself and would go untested.
- **Whole-system tests** live under `tests/e2e/`, named `test_*.py`. They'll run the full
  path (API request → worker → assessment) once those parts exist.

Run everything with `uv run pytest`.
