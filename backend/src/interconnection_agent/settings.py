"""Settings for anything that calls the model: the API key and the spending limits.

Values come from the process environment first and a local ``.env`` file second, so a
developer can keep the key in ``.env`` (which git ignores) while CI or a shell export can
still override it. ``load_settings`` takes both sources as arguments so tests never touch
the real environment and never need a live key.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from interconnection_agent.budget import Limits


class SettingsError(ValueError):
    """A required setting is missing or has a value that cannot be used."""


@dataclass(frozen=True)
class Settings:
    """What a model-calling run needs. The key is left out of ``repr`` so logs cannot leak it."""

    api_key: str = field(repr=False)
    limits: Limits = Limits()


# Which environment variable sets which field of ``Limits``.
LIMIT_VARIABLES: dict[str, str] = {
    "AGENT_MAX_TURNS": "max_turns",
    "AGENT_MAX_TOKENS_PER_ASSESSMENT": "max_tokens_per_assessment",
    "AGENT_MAX_OUTPUT_TOKENS_PER_CALL": "max_output_tokens_per_call",
}


def load_settings(environ: Mapping[str, str], dotenv_path: Path) -> Settings:
    """Build settings from ``environ``, falling back to the ``.env`` file at ``dotenv_path``."""
    merged = {k: v for k, v in dotenv_values(dotenv_path).items() if v is not None}
    merged.update(environ)
    api_key = merged.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise SettingsError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in, "
            "or export it in your shell."
        )
    overrides = {
        field_name: _positive_int(variable, merged[variable])
        for variable, field_name in LIMIT_VARIABLES.items()
        if variable in merged
    }
    return Settings(api_key=api_key, limits=Limits(**overrides))


def _positive_int(variable: str, raw: str) -> int:
    """Parse a limit, refusing anything that is not a whole number above zero.

    Zero is refused too: a limit of zero would make every request fail, which is never
    what someone setting the variable meant.
    """
    problem = SettingsError(f"{variable} must be a whole number above zero, got {raw!r}.")
    try:
        value = int(raw.strip())
    except ValueError:
        raise problem from None
    if value <= 0:
        raise problem
    return value
