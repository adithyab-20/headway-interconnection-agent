"""Run the API: ``python -m interconnection_agent.api [--port 8000]``.

Written assessments use Claude when ``ANTHROPIC_API_KEY`` is set (in the environment or
``.env``); without it, everything but writing and asking works. The model
(``ANTHROPIC_MODEL``) and the public site's limits (``WRITE_UPS_PER_VISITOR_PER_DAY``,
``WRITE_UPS_PER_DAY``, ``SPEND_LIMIT_PER_MONTH_USD``) are set the same way.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from interconnection_agent.api import create_app
from interconnection_agent.assessment import Claude, Model
from interconnection_agent.db import connect
from interconnection_agent.settings import SettingsError, load_settings, load_site_limits
from interconnection_agent.spending import Metered


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Headway's API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()

    site_limits = load_site_limits(os.environ, Path(".env"))
    try:
        settings = load_settings(os.environ, Path(".env"))
    except SettingsError:
        settings = None
    claude: Model | None = (
        Metered(
            Claude(settings),
            priced_as=settings.model,
            limit_usd=site_limits.spend_per_month_usd,
            connect=connect,
        )
        if settings
        else None
    )
    app = create_app(
        lambda: claude,
        limits=settings.limits if settings else None,
        site_limits=site_limits,
    )
    uvicorn.run(app, host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
