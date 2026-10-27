"""Ejecuta las alertas contra Gold y las escribe en un log local."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from etl_running.alerts.rules import Alert, AlertContext, evaluate
from etl_running.common.config import Settings


class AlertsError(RuntimeError):
    """No se pudieron evaluar las alertas."""


@dataclass(frozen=True)
class AlertResult:
    alerts: list[Alert]
    context: AlertContext
    log_path: Path


def _read_context(settings: Settings, now: datetime) -> AlertContext:
    warehouse = settings.warehouse_path
    if not warehouse.is_file():
        raise AlertsError(
            f"No existe el warehouse {warehouse}; ejecuta `make dbt-build` "
            "o `make demo` antes de lanzar alertas."
        )
    try:
        with duckdb.connect(str(warehouse), read_only=True) as con:
            last_run = con.execute("select max(activity_date) from gold.fct_runs").fetchone()[0]
            acwr_row = con.execute(
                """
                select acwr, is_reliable from gold.fct_training_load
                where acwr is not null order by activity_date desc limit 1
                """
            ).fetchone()
            compliance = con.execute(
                """
                select plan_compliance_pct from gold.fct_weekly_summary
                where plan_compliance_pct is not null
                order by week_start desc limit 1
                """
            ).fetchone()
    except duckdb.Error as exc:
        raise AlertsError(f"No se pudo consultar Gold: {exc}") from exc

    now_utc = now if now.tzinfo else now.replace(tzinfo=UTC)
    modified = datetime.fromtimestamp(warehouse.stat().st_mtime, tz=UTC)
    days_since = (now_utc.date() - last_run).days if last_run else None
    api_key_days_left = (
        (settings.api_key_expires - now_utc.date()).days if settings.api_key_expires else None
    )
    return AlertContext(
        acwr=acwr_row[0] if acwr_row else None,
        acwr_reliable=bool(acwr_row[1]) if acwr_row else False,
        days_since_last_run=days_since,
        plan_compliance_pct=compliance[0] if compliance else None,
        data_age_hours=(now_utc - modified).total_seconds() / 3600.0,
        api_key_days_left=api_key_days_left,
    )


def run_alerts(
    settings: Settings,
    *,
    log_path: Path | str | None = None,
    now: datetime | None = None,
) -> AlertResult:
    """Evalúa las reglas y añade una línea por aviso (o una de “sin avisos”)."""
    current = now or datetime.now(UTC)
    context = _read_context(settings, current)
    alerts = evaluate(context)
    target = Path(log_path) if log_path else settings.lake_dir / "alerts.log"
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = [alert.as_log_line(current) for alert in alerts]
    if not lines:
        lines = [
            f"{current.strftime('%Y-%m-%dT%H:%M:%SZ')} | INFO | no_alerts | "
            "Sin avisos con las reglas actuales."
        ]
    with target.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return AlertResult(alerts=alerts, context=context, log_path=target)
