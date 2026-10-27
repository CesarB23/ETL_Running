"""CLI de ETL_Running (argparse)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from etl_running import __version__
from etl_running.bronze.report import (
    build_report,
    format_activities,
    format_report,
    latest_activities,
)
from etl_running.common.config import ConfigError, DateOutsideWindowError, Settings
from etl_running.common.logging import configure_logging
from etl_running.ingest.fit_download import download_pending, pending_fits
from etl_running.ingest.garmin_client import open_client
from etl_running.ingest.pipeline import (
    DEFAULT_LOOKBACK,
    IngestSummary,
    WindowError,
    resolve_window,
    run_ingest,
    runs_log_path,
)
from etl_running.ingest.plan_loader import PlanError, load_week
from etl_running.silver.build import build_silver
from etl_running.silver.fit_build import build_fit
from etl_running.silver.plan_build import build_plan
from etl_running.silver.plan_confirmations import confirm_match
from etl_running.silver.plan_links import collect_links
from etl_running.silver.report import format_silver_report
from etl_running.tools.show_run import render_run


def _since(raw: str) -> str | date:
    if raw == "last":
        return "last"
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("usa 'last' o YYYY-MM-DD") from exc


def _day(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("usa el formato YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="etl_running",
        description="Plataforma de datos personal sobre actividades de running de Garmin.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de logging (por defecto: INFO).",
    )
    parser.add_argument(
        "--log-format",
        default="text",
        choices=["text", "json"],
        help="Formato de logs: text (legible, por defecto) o json.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMANDO", required=True)
    subparsers.add_parser("version", help="Muestra la versión.")
    subparsers.add_parser("config", help="Muestra la configuración efectiva (sin secretos).")

    ingest = subparsers.add_parser("ingest", help="Descarga lo nuevo a bronze (incremental).")
    ingest.add_argument("--since", type=_since, default="last", help="'last' o YYYY-MM-DD.")
    ingest.add_argument("--until", type=_day, default=None, help="YYYY-MM-DD (por defecto: hoy).")
    ingest.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK,
        help=f"Días a releer desde el cursor (por defecto: {DEFAULT_LOOKBACK}).",
    )

    backfill = subparsers.add_parser(
        "backfill", help="Carga el historial desde START_DATE (reanudable)."
    )
    backfill.add_argument("--from", dest="from_", type=_day, default=None, help="YYYY-MM-DD.")
    backfill.add_argument("--to", type=_day, default=None, help="YYYY-MM-DD (por defecto: hoy).")

    bronze = subparsers.add_parser("bronze", help="Utilidades sobre bronze.")
    bronze_sub = bronze.add_subparsers(dest="bronze_command", metavar="SUBCOMANDO", required=True)
    bronze_sub.add_parser("report", help="Filas, rango, frescura, errores y typeKey.")
    show = bronze_sub.add_parser("show", help="Lista actividades de bronze (solo lectura).")
    show.add_argument(
        "--last-days", type=int, default=7, help="Últimos N días incluido hoy (por defecto: 7)."
    )
    silver = subparsers.add_parser("silver", help="Tablas limpias (solo running).")
    silver_sub = silver.add_subparsers(dest="silver_command", metavar="SUBCOMANDO", required=True)
    build = silver_sub.add_parser("build", help="Construye silver.activities desde bronze.")
    build.add_argument(
        "--full-refresh", action="store_true", help="Reconstruye todo ignorando el estado previo."
    )
    build.add_argument(
        "--only",
        nargs="+",
        choices=["activity_laps", "activity_records", "planned_workouts", "planned_steps"],
        help="Par FIT o par de tablas del plan (siempre juntas).",
    )
    silver_sub.add_parser("report", help="Reconciliación con bronze, alcance y cobertura.")
    fit = subparsers.add_parser("fit", help="Descarga FIT originales de carreras.")
    fit_sub = fit.add_subparsers(dest="fit_command", required=True)
    download = fit_sub.add_parser("download", help="Descarga FIT pendientes en bronze.")
    download.add_argument("--pending", action="store_true", help="Solo pendientes (por defecto).")
    show_run = subparsers.add_parser("show-run", help="Genera HTML con gráfica y laps.")
    show_run.add_argument("activity_id", type=int)
    show_run.add_argument("--out", type=Path, required=True)
    plan = subparsers.add_parser("plan", help="Carga planes semanales JSON a bronze.")
    plan_sub = plan.add_subparsers(dest="plan_command", required=True)
    load = plan_sub.add_parser("load", help="Carga un JSON de semana desde Garmin/workouts.")
    load.add_argument("path", type=Path)
    link = plan_sub.add_parser("link-workouts", help="Vincula nombre API con uploads locales.")
    link.add_argument("--refresh", action="store_true", help="Reconsultar la API.")
    confirm = plan_sub.add_parser("confirm", help="Confirma actividad corrida para una sesión.")
    confirm.add_argument("--date", type=_day, required=True, help="Fecha planificada.")
    confirm.add_argument("--activity-id", type=int, required=True)
    report = subparsers.add_parser("plan-report", help="Cumplimiento semanal plan vs real.")
    report.add_argument("--week", type=_day, required=True)

    alerts = subparsers.add_parser("alerts", help="Reglas de alerta sobre Gold.")
    alerts_sub = alerts.add_subparsers(dest="alerts_command", metavar="SUBCOMANDO", required=True)
    alerts_run = alerts_sub.add_parser("run", help="Evalúa y escribe lake/alerts.log.")
    alerts_run.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Ruta alternativa del log (por defecto: lake/alerts.log).",
    )
    return parser


def _cmd_version() -> int:
    print(f"etl_running {__version__}")
    return 0


def _cmd_config(settings: Settings) -> int:
    print(f"start_date:        {settings.start_date.isoformat()}")
    print(f"lake_dir:          {settings.lake_dir}")
    print(f"running_type_keys: {', '.join(settings.running_type_keys)}")
    print(f"api_key:           {'definida' if settings.api_key else 'no definida'}")
    print(
        "api_key_caduca:    "
        f"{settings.api_key_expires.isoformat() if settings.api_key_expires else 'no informada'}"
    )
    return 0


def _print_summary(summary: IngestSummary) -> None:
    print(f"run_id:           {summary.run_id}")
    print(f"ventana:          {summary.since} → {summary.until} ({summary.days} días)")
    print(f"actividades API:  {summary.fetched}")
    print(f"archivos nuevos:  {summary.files_written}")
    print(f"sin cambios:      {summary.files_skipped}")


def _cmd_ingest(settings: Settings, args: argparse.Namespace) -> int:
    resume = args.command == "backfill"
    if resume:
        since, until, lookback = args.from_, args.to, DEFAULT_LOOKBACK
    else:
        since, until, lookback = args.since, args.until, args.lookback
    start, end = resolve_window(
        settings, since=since, until=until, lookback=lookback, resume=resume, today=date.today()
    )
    with open_client(settings) as client:
        _print_summary(run_ingest(settings, client, start, end))
    return 0


def _cmd_bronze_report(settings: Settings) -> int:
    reports = build_report(settings.bronze_dir, runs_log_path(settings.lake_dir))
    print(format_report(reports, settings.running_type_keys))
    return 0


def _cmd_bronze_show(settings: Settings, last_days: int) -> int:
    if last_days < 1:
        print("Error: --last-days debe ser >= 1", file=sys.stderr)
        return 2
    since = date.today() - timedelta(days=last_days - 1)
    activities = latest_activities(settings.bronze_dir, since)
    print(f"Actividades desde {since} (bronze, solo lectura):\n")
    print(format_activities(activities, settings.running_type_keys))
    return 0


def _cmd_silver(settings: Settings, args: argparse.Namespace) -> int:
    if args.silver_command == "report":
        print(format_silver_report(settings.silver_dir, settings.running_type_keys))
        return 0
    if args.only:
        if set(args.only) == {"activity_laps", "activity_records"}:
            result = build_fit(settings)
            print(
                f"FIT: {result['fits']} | laps: {result['laps']} | "
                f"records: {result['records']} | excepciones: {len(result['exceptions'])}"
            )
        elif set(args.only) == {"planned_workouts", "planned_steps"}:
            result = build_plan(settings, Path("../Garmin/data/uploads.json"))
            print(
                f"Plan: {result['weeks']} semanas | {result['sessions']} sesiones | "
                f"{result['steps']} pasos | {result['uploaded_ids']} IDs Garmin"
            )
        else:
            raise ValueError(
                "--only requiere activity_laps/activity_records o "
                "planned_workouts/planned_steps juntos"
            )
        return 0
    result = build_silver(settings, full_refresh=args.full_refresh)
    build_plan(settings, Path("../Garmin/data/uploads.json"))
    print(f"silver:        {result.silver} actividades de running")
    print(f"cuarentena:    {result.quarantine}")
    print(f"out_of_scope:  {result.out_of_scope_total}")
    print(f"estado:        {'sin cambios' if result.skipped or not result.wrote else 'escrito'}")
    print(f"reconcilia:    {'sí' if result.reconciles else 'NO'}")
    return 0 if result.reconciles else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "version":
        return _cmd_version()

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2

    configure_logging(args.log_level, settings.secrets(), fmt=args.log_format)

    try:
        if args.command == "config":
            return _cmd_config(settings)
        if args.command == "alerts":
            from etl_running.alerts.runner import run_alerts

            result = run_alerts(settings, log_path=args.log_file)
            for alert in result.alerts:
                print(f"{alert.severity.upper():8} {alert.code}: {alert.message}")
            if not result.alerts:
                print("Sin avisos con las reglas actuales.")
            print(f"alertas: {len(result.alerts)} | log: {result.log_path}")
            return 0
        if args.command == "plan":
            if args.plan_command == "load":
                print("Plan cargado" if load_week(settings, args.path) else "Plan sin cambios")
            elif args.plan_command == "confirm":
                updated = confirm_match(settings, args.date, args.activity_id)
                print("Asociación confirmada" if updated else "Asociación ya confirmada")
            else:
                with open_client(settings) as client:
                    count = collect_links(settings, client, refresh=args.refresh)
                    print(f"Workouts enlazados: {count}")
            return 0
        if args.command == "plan-report":
            from etl_running.gold.plan_report import report_week

            print(report_week(settings, args.week))
            return 0
        if args.command in ("ingest", "backfill"):
            return _cmd_ingest(settings, args)
        if args.command == "fit":
            pending, excluded = pending_fits(settings)
            print(f"Pendientes: {len(pending)} | excluidos: {dict(excluded)}")
            if pending:
                with open_client(settings) as client:
                    print(f"Resultado: {dict(download_pending(settings, client))}")
            return 0
        if args.command == "show-run":
            print(render_run(settings.silver_dir, args.activity_id, args.out))
            return 0
        if args.command == "silver":
            return _cmd_silver(settings, args)
        if args.command == "bronze":
            return (
                _cmd_bronze_show(settings, args.last_days)
                if args.bronze_command == "show"
                else _cmd_bronze_report(settings)
            )
    except (ConfigError, DateOutsideWindowError, WindowError, PlanError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 2
