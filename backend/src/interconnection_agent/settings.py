"""Settings for anything that calls the model: the API key, the model, and the limits.

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
from interconnection_agent.spending import PRICES

DEFAULT_MODEL = "claude-sonnet-5-5"


class SettingsError(ValueError):
    """A required setting is missing or has a value that cannot be used."""


@dataclass(frozen=True)
class Settings:
    """What a model-calling run needs. The key is left out of ``repr`` so logs cannot leak it."""

    api_key: str = field(repr=False)
    limits: Limits = Limits()
    model: str = DEFAULT_MODEL


@dataclass(frozen=True)
class SiteLimits:
    """How much the public site may use the model. Zero turns write-ups off."""

    write_ups_per_visitor_per_day: int = 3
    write_ups_per_day: int = 20
    spend_per_month_usd: float = 10.0


# Which environment variable sets which field of ``Limits``.
LIMIT_VARIABLES: dict[str, str] = {
    "AGENT_MAX_TURNS": "max_turns",
    "AGENT_MAX_TOKENS_PER_ASSESSMENT": "max_tokens_per_assessment",
    "AGENT_MAX_OUTPUT_TOKENS_PER_CALL": "max_output_tokens_per_call",
}


def load_settings(environ: Mapping[str, str], dotenv_path: Path) -> Settings:
    """Build settings from ``environ``, falling back to the ``.env`` file at ``dotenv_path``."""
    merged = _merged(environ, dotenv_path)
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
    model = merged.get("ANTHROPIC_MODEL", DEFAULT_MODEL).strip()
    if model not in PRICES:
        raise SettingsError(
            f"ANTHROPIC_MODEL must be one of {', '.join(sorted(PRICES))}, got {model!r}."
        )
    return Settings(api_key=api_key, limits=Limits(**overrides), model=model)


def load_site_limits(environ: Mapping[str, str], dotenv_path: Path) -> SiteLimits:
    """The public site's limits, from ``environ`` first and the ``.env`` file second."""
    merged = _merged(environ, dotenv_path)
    defaults = SiteLimits()
    return SiteLimits(
        write_ups_per_visitor_per_day=_whole_number(
            "WRITE_UPS_PER_VISITOR_PER_DAY", merged, defaults.write_ups_per_visitor_per_day
        ),
        write_ups_per_day=_whole_number("WRITE_UPS_PER_DAY", merged, defaults.write_ups_per_day),
        spend_per_month_usd=_dollars(
            "SPEND_LIMIT_PER_MONTH_USD", merged, defaults.spend_per_month_usd
        ),
    )


def _merged(environ: Mapping[str, str], dotenv_path: Path) -> dict[str, str]:
    merged = {k: v for k, v in dotenv_values(dotenv_path).items() if v is not None}
    merged.update(environ)
    return merged


def _whole_number(variable: str, merged: Mapping[str, str], default: int) -> int:
    if variable not in merged:
        return default
    raw = merged[variable]
    problem = SettingsError(f"{variable} must be a whole number, zero or more, got {raw!r}.")
    try:
        value = int(raw.strip())
    except ValueError:
        raise problem from None
    if value < 0:
        raise problem
    return value


def _dollars(variable: str, merged: Mapping[str, str], default: float) -> float:
    if variable not in merged:
        return default
    raw = merged[variable]
    problem = SettingsError(f"{variable} must be an amount in dollars, zero or more, got {raw!r}.")
    try:
        value = float(raw.strip())
    except ValueError:
        raise problem from None
    if not value >= 0:
        raise problem
    return value


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
