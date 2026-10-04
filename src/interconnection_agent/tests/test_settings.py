"""Unit tests for :mod:`interconnection_agent.settings`.

Pure logic only: every test hands ``load_settings`` its own environment mapping and its
own ``.env`` path, so nothing here reads the developer's real environment or calls the API.
"""

from pathlib import Path

import pytest

from interconnection_agent.settings import SettingsError, load_settings

KEY_ONLY = {"ANTHROPIC_API_KEY": "sk-test"}


def write_env(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_reads_api_key_from_env_file(tmp_path: Path) -> None:
    dotenv = write_env(tmp_path, "ANTHROPIC_API_KEY=sk-test-from-file\n")

    settings = load_settings(environ={}, dotenv_path=dotenv)

    assert settings.api_key == "sk-test-from-file"


def test_process_environment_beats_env_file(tmp_path: Path) -> None:
    dotenv = write_env(tmp_path, "ANTHROPIC_API_KEY=sk-test-from-file\n")

    settings = load_settings(
        environ={"ANTHROPIC_API_KEY": "sk-test-from-shell"}, dotenv_path=dotenv
    )

    assert settings.api_key == "sk-test-from-shell"


def test_missing_env_file_is_fine_when_the_key_is_exported(tmp_path: Path) -> None:
    settings = load_settings(
        environ={"ANTHROPIC_API_KEY": "sk-test-from-shell"}, dotenv_path=tmp_path / "absent.env"
    )

    assert settings.api_key == "sk-test-from-shell"


@pytest.mark.parametrize("env_text", ["", "ANTHROPIC_API_KEY=\n", "ANTHROPIC_API_KEY=   \n"])
def test_missing_or_blank_key_is_a_clear_error(tmp_path: Path, env_text: str) -> None:
    dotenv = write_env(tmp_path, env_text)

    with pytest.raises(SettingsError, match=r"ANTHROPIC_API_KEY.*\.env\.example"):
        load_settings(environ={}, dotenv_path=dotenv)


def test_printing_settings_does_not_reveal_the_key(tmp_path: Path) -> None:
    settings = load_settings(
        environ={"ANTHROPIC_API_KEY": "sk-test-do-not-print"}, dotenv_path=tmp_path / "absent.env"
    )

    assert "sk-test-do-not-print" not in repr(settings)
    assert "sk-test-do-not-print" not in str(settings)


def test_limits_have_defaults(tmp_path: Path) -> None:
    settings = load_settings(environ=KEY_ONLY, dotenv_path=tmp_path / "absent.env")

    assert settings.limits.max_turns == 10
    assert settings.limits.max_tokens_per_assessment == 200_000
    assert settings.limits.max_output_tokens_per_call == 16_000


def test_limits_can_be_set_from_the_environment(tmp_path: Path) -> None:
    environ = {
        **KEY_ONLY,
        "AGENT_MAX_TURNS": "3",
        "AGENT_MAX_TOKENS_PER_ASSESSMENT": "50000",
        "AGENT_MAX_OUTPUT_TOKENS_PER_CALL": "4000",
    }

    settings = load_settings(environ=environ, dotenv_path=tmp_path / "absent.env")

    assert settings.limits.max_turns == 3
    assert settings.limits.max_tokens_per_assessment == 50_000
    assert settings.limits.max_output_tokens_per_call == 4_000


@pytest.mark.parametrize("bad_value", ["abc", "0", "-5", "", "2.5"])
def test_unusable_limit_is_a_clear_error(tmp_path: Path, bad_value: str) -> None:
    environ = {**KEY_ONLY, "AGENT_MAX_TURNS": bad_value}

    with pytest.raises(SettingsError, match="AGENT_MAX_TURNS"):
        load_settings(environ=environ, dotenv_path=tmp_path / "absent.env")
