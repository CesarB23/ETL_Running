from __future__ import annotations

import pytest

from etl_running import __version__
from etl_running.cli import build_parser, main


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "etl_running" in out
    assert "version" in out
    assert "config" in out


def test_version(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == f"etl_running {__version__}"


def test_command_is_required():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([])
    assert exc.value.code == 2


def test_config_never_prints_the_key(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "super-secret-key-123")
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert "super-secret-key-123" not in out
    assert "definida" in out
    assert "2026-08-17" in out


def test_config_reports_invalid_values(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("START_DATE", "no-es-fecha")
    assert main(["config"]) == 2
    assert "START_DATE" in capsys.readouterr().err
