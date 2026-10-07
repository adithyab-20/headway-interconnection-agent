"""Where the API key and spending limits come from, and how bad values are reported.

Every test passes its own environment and ``.env`` path, so nothing reads the developer's
real environment or calls the API.
"""

from pathlib import Path

import pytest

from interconnection_agent.settings import SettingsError, load_settings

KEY_ONLY = {"ANTHROPIC_API_KEY": "sk-test"}


def test_the_key_comes_from_env_file_and_a_real_environment_variable_wins(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("ANTHROPIC_API_KEY=sk-test-from-file\n")

    assert load_settings(environ={}, dotenv_path=dotenv).api_key == "sk-test-from-file"
    shell = {"ANTHROPIC_API_KEY": "sk-test-from-shell"}
    assert load_settings(environ=shell, dotenv_path=dotenv).api_key == "sk-test-from-shell"
    assert (
        load_settings(environ=shell, dotenv_path=tmp_path / "absent").api_key
        == "sk-test-from-shell"
    )


@pytest.mark.parametrize("env_text", ["", "ANTHROPIC_API_KEY=\n", "ANTHROPIC_API_KEY=   \n"])
def test_a_missing_or_blank_key_is_a_clear_error(tmp_path: Path, env_text: str) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(env_text)
    with pytest.raises(SettingsError, match=r"ANTHROPIC_API_KEY.*\.env\.example"):
        load_settings(environ={}, dotenv_path=dotenv)


def test_printing_settings_never_shows_the_key(tmp_path: Path) -> None:
    settings = load_settings(
        environ={"ANTHROPIC_API_KEY": "sk-test-do-not-print"}, dotenv_path=tmp_path / "absent"
    )
    assert "sk-test-do-not-print" not in repr(settings) + str(settings)


@pytest.mark.parametrize("bad_value", ["abc", "0", "-5", "", "2.5"])
def test_limits_have_defaults_can_be_changed_and_bad_values_are_refused(
    tmp_path: Path, bad_value: str
) -> None:
    absent = tmp_path / "absent"
    defaults = load_settings(environ=KEY_ONLY, dotenv_path=absent).limits
    assert (
        defaults.max_turns,
        defaults.max_tokens_per_assessment,
        defaults.max_output_tokens_per_call,
    ) == (10, 200_000, 16_000)

    changed = load_settings(
        environ={
            **KEY_ONLY,
            "AGENT_MAX_TURNS": "3",
            "AGENT_MAX_TOKENS_PER_ASSESSMENT": "50000",
            "AGENT_MAX_OUTPUT_TOKENS_PER_CALL": "4000",
        },
        dotenv_path=absent,
    ).limits
    assert (
        changed.max_turns,
        changed.max_tokens_per_assessment,
        changed.max_output_tokens_per_call,
    ) == (3, 50_000, 4_000)

    with pytest.raises(SettingsError, match="AGENT_MAX_TURNS"):
        load_settings(environ={**KEY_ONLY, "AGENT_MAX_TURNS": bad_value}, dotenv_path=absent)
