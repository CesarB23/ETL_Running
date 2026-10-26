from __future__ import annotations

import etl_running
from etl_running.common.config import Settings


def test_package_imports():
    assert isinstance(etl_running.__version__, str)


def test_settings_load_from_empty_env():
    settings = Settings.from_env(env={}, dotenv_path=None)
    assert settings.start_date.isoformat() == "2026-08-17"
