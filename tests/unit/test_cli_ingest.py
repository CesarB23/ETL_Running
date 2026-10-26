from __future__ import annotations

from contextlib import contextmanager

import pytest
from tests.unit.fakes import FakeClient

from etl_running import cli


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LAKE_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "k-123")


def fake_open(activities):
    @contextmanager
    def _open(settings):
        yield FakeClient(activities)

    return _open


def test_backfill_before_start_date_is_rejected(env, capsys):
    assert cli.main(["backfill", "--from", "2026-08-01"]) == 2
    assert "anterior al inicio de la ventana" in capsys.readouterr().err


def test_ingest_without_api_key_fails_cleanly(env, monkeypatch, capsys):
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "")
    assert cli.main(["ingest"]) == 2
    assert "GARMIN_PERSONAL_API_KEY" in capsys.readouterr().err


def test_backfill_ingest_and_report_end_to_end(env, monkeypatch, capsys, activities_fixture):
    monkeypatch.setattr(cli, "open_client", fake_open(activities_fixture))
    assert cli.main(["backfill"]) == 0
    assert "archivos nuevos" in capsys.readouterr().out

    assert cli.main(["ingest", "--since", "last"]) == 0
    assert "archivos nuevos:  0" in capsys.readouterr().out

    assert cli.main(["bronze", "report"]) == 0
    out = capsys.readouterr().out
    assert "garmin/activities_list" in out
    assert "typeKey" in out
    assert "k-123" not in out


def test_bronze_show(env, monkeypatch, capsys, activities_fixture):
    monkeypatch.setattr(cli, "open_client", fake_open(activities_fixture))
    assert cli.main(["bronze", "show"]) == 0
    assert "Sin actividades" in capsys.readouterr().out
    assert cli.main(["bronze", "show", "--last-days", "0"]) == 2
