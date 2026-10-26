"""Plataforma de datos personal sobre actividades de running de Garmin Connect."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("etl-running")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
