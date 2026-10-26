"""CLI de ETL_Running (argparse)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, timedelta

from etl_running import __version__
from etl_running.bronze.report import (
    build_report,
    format_activities,
    format_report,
    latest_activities,
)
from etl_running.common.config import ConfigError, DateOutsideWindowError, Settings
from etl_running.common.logging import configure_logging
from etl_running.ingest.garmin_client import open_client
from etl_running.ingest.pipeline import (
    DEFAULT_LOOKBACK,
    IngestSummary,
    WindowError,
    resolve_window,
    run_ingest,
    runs_log_path,
)


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
    return parser


def _cmd_version() -> int:
    print(f"etl_running {__version__}")
    return 0


def _cmd_config(settings: Settings) -> int:
    print(f"start_date:        {settings.start_date.isoformat()}")
    print(f"lake_dir:          {settings.lake_dir}")
    print(f"running_type_keys: {', '.join(settings.running_type_keys)}")
    print(f"api_key:           {'definida' if settings.api_key else 'no definida'}")
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
        if args.command in ("ingest", "backfill"):
            return _cmd_ingest(settings, args)
        if args.command == "bronze":
            return (
                _cmd_bronze_show(settings, args.last_days)
                if args.bronze_command == "show"
                else _cmd_bronze_report(settings)
            )
    except (ConfigError, DateOutsideWindowError, WindowError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 2
