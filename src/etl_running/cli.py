"""CLI de ETL_Running (argparse)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from etl_running import __version__
from etl_running.common.config import ConfigError, Settings
from etl_running.common.logging import configure_logging


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
    subparsers = parser.add_subparsers(dest="command", metavar="COMANDO", required=True)
    subparsers.add_parser("version", help="Muestra la versión.")
    subparsers.add_parser("config", help="Muestra la configuración efectiva (sin secretos).")
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "version":
        return _cmd_version()

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2

    configure_logging(args.log_level, settings.secrets())

    if args.command == "config":
        return _cmd_config(settings)
    return 2
