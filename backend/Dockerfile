# Headway's API, as Railway runs it (see railway.toml). Built from this folder.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Packages first, so a code change doesn't reinstall them. Dev tools (tests, the browser,
# fuzzy matching) are left out.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY data ./data
RUN uv sync --locked --no-dev

# Railway says which port to listen on.
CMD python -m interconnection_agent.api --host 0.0.0.0 --port ${PORT:-8000}
