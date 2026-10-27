from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from etl_running.alerts.rules import (
    AlertContext,
    acwr_alert,
    api_key_expiry_alert,
    compliance_alert,
    evaluate,
    freshness_alert,
    inactivity_alert,
)
from etl_running.alerts.runner import AlertsError, run_alerts
from etl_running.common.config import Settings
from etl_running.demo.warehouse import build_demo_warehouse


def test_acwr_requires_reliable_window():
    assert acwr_alert(AlertContext(acwr=1.8, acwr_reliable=False)) == []
    assert acwr_alert(AlertContext(acwr=1.5, acwr_reliable=True)) == []
    alerts = acwr_alert(AlertContext(acwr=1.51, acwr_reliable=True))
    assert [a.code for a in alerts] == ["acwr_high"]
    assert alerts[0].severity == "warning"


def test_inactivity_threshold():
    assert inactivity_alert(AlertContext(days_since_last_run=10)) == []
    alerts = inactivity_alert(AlertContext(days_since_last_run=11))
    assert alerts[0].code == "inactivity"


def test_compliance_threshold():
    assert compliance_alert(AlertContext(plan_compliance_pct=None)) == []
    assert compliance_alert(AlertContext(plan_compliance_pct=50)) == []
    assert compliance_alert(AlertContext(plan_compliance_pct=49.9))[0].code == (
        "plan_compliance_low"
    )


def test_freshness_threshold():
    assert freshness_alert(AlertContext(data_age_hours=36)) == []
    assert freshness_alert(AlertContext(data_age_hours=36.1))[0].code == "data_stale"


def test_api_key_expiry_and_expired():
    assert api_key_expiry_alert(AlertContext(api_key_days_left=15)) == []
    assert api_key_expiry_alert(AlertContext(api_key_days_left=14))[0].code == ("api_key_expiring")
    expired = api_key_expiry_alert(AlertContext(api_key_days_left=-2))
    assert expired[0].code == "api_key_expired"
    assert expired[0].severity == "critical"


def test_evaluate_returns_stable_order():
    context = AlertContext(
        acwr=1.8,
        acwr_reliable=True,
        days_since_last_run=12,
        plan_compliance_pct=20,
        data_age_hours=48,
        api_key_days_left=3,
    )
    assert [alert.code for alert in evaluate(context)] == [
        "acwr_high",
        "inactivity",
        "plan_compliance_low",
        "data_stale",
        "api_key_expiring",
    ]


def test_run_alerts_appends_to_log(tmp_path: Path):
    warehouse = build_demo_warehouse(tmp_path / "warehouse.duckdb", weeks=8)
    settings = Settings(lake_dir=warehouse.parent)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    result = run_alerts(settings, log_path=tmp_path / "alerts.log", now=now)
    lines = result.log_path.read_text(encoding="utf-8").splitlines()
    assert result.alerts
    assert any("plan_compliance_low" in line for line in lines)
    assert warehouse.is_file()


def test_run_alerts_writes_no_alerts_marker(tmp_path: Path, monkeypatch):
    warehouse = build_demo_warehouse(tmp_path / "warehouse.duckdb")
    settings = Settings(lake_dir=warehouse.parent)
    # El warehouse demo tiene cumplimiento bajo; se fuerza una fecha futura
    # solo para comprobar el marcador de “sin avisos” con reglas desactivadas.
    monkeypatch.setattr(
        "etl_running.alerts.runner.evaluate",
        lambda context: [],
    )
    result = run_alerts(settings, log_path=tmp_path / "alerts.log")
    text = result.log_path.read_text(encoding="utf-8")
    assert "no_alerts" in text


def test_run_alerts_requires_warehouse(tmp_path: Path):
    settings = Settings(lake_dir=tmp_path / "lake")
    with pytest.raises(AlertsError):
        run_alerts(settings, log_path=tmp_path / "alerts.log")


def test_settings_parses_api_key_expiry():
    settings = Settings.from_env(env={"GARMIN_API_KEY_EXPIRES": "2026-12-01"}, dotenv_path=None)
    assert settings.api_key_expires == date(2026, 12, 1)
    assert Settings.from_env(env={}, dotenv_path=None).api_key_expires is None


def test_log_line_has_utc_timestamp():
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    line = AlertContext(acwr=1.8, acwr_reliable=True)
    alert = acwr_alert(line)[0]
    assert alert.as_log_line(now).startswith("2026-10-26T12:00:00Z | WARNING | acwr_high")


def test_freshness_uses_whole_hours():
    assert freshness_alert(AlertContext(data_age_hours=timedelta(hours=37).total_seconds() / 3600))


def test_cli_alerts_writes_log(monkeypatch, tmp_path: Path, capsys):
    from etl_running.cli import main

    build_demo_warehouse(tmp_path / "warehouse.duckdb")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LAKE_DIR", str(tmp_path))
    log = tmp_path / "alerts.log"
    assert main(["alerts", "run", "--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "alertas:" in out
    assert log.is_file()
    assert "plan_compliance_low" in log.read_text(encoding="utf-8")
