from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from etl_running.common.config import (
    ConfigError,
    DateOutsideWindowError,
    Settings,
    parse_dotenv,
)

SECRET = "super-secret-key-123"
API_KEY_VAR = "GARMIN_PERSONAL_API_KEY"


def test_defaults():
    settings = Settings.from_env(env={}, dotenv_path=None)
    assert settings.start_date == date(2026, 8, 17)
    assert settings.lake_dir == Path("lake")
    assert "running" in settings.running_type_keys
    assert settings.api_key is None


def test_env_overrides_dotenv(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("LAKE_DIR=from_file\nSTART_DATE=2026-09-01\n", encoding="utf-8")
    settings = Settings.from_env(env={"LAKE_DIR": "from_env"}, dotenv_path=dotenv)
    assert settings.lake_dir == Path("from_env")
    assert settings.start_date == date(2026, 9, 1)


def test_derived_paths():
    settings = Settings(lake_dir=Path("x"))
    assert settings.bronze_dir == Path("x/bronze")
    assert settings.silver_dir == Path("x/silver")
    assert settings.gold_dir == Path("x/gold")
    assert settings.warehouse_path == Path("x/warehouse.duckdb")


def test_window_rejects_dates_before_start():
    settings = Settings()
    assert settings.ensure_in_window(date(2026, 8, 17)) == date(2026, 8, 17)
    with pytest.raises(DateOutsideWindowError):
        settings.ensure_in_window(date(2026, 8, 16))


def test_invalid_start_date():
    with pytest.raises(ConfigError):
        Settings.from_env(env={"START_DATE": "17/08/2026"}, dotenv_path=None)


def test_empty_running_keys_rejected():
    with pytest.raises(ConfigError):
        Settings.from_env(env={"RUNNING_TYPE_KEYS": " , "}, dotenv_path=None)


def test_custom_running_keys():
    settings = Settings.from_env(env={"RUNNING_TYPE_KEYS": "running, trail_running"})
    assert settings.running_type_keys == ("running", "trail_running")


def test_api_key_never_in_repr_or_secrets_leak():
    settings = Settings.from_env(env={API_KEY_VAR: SECRET}, dotenv_path=None)
    assert settings.api_key == SECRET
    assert SECRET not in repr(settings)
    assert settings.secrets() == (SECRET,)


def test_parse_dotenv_handles_comments_quotes_and_export():
    text = "# comentario\n\nexport A='1'\nB=\"two\"\nC=3 \nsin_igual\n"
    assert parse_dotenv(text) == {"A": "1", "B": "two", "C": "3"}
