"""Logging con redacción de secretos: texto legible (estilo Airflow) o JSON."""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TextIO

REDACTED = "***"

_PATTERNS = (
    re.compile(r"(?i)((?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)([\"']?(?:api[_-]?key|access[_-]?token|token|password|passwd|secret)"
        r"[\"']?\s*[=:]\s*[\"']?)[^\s,;\"'}]+"
    ),
)

_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("x", logging.INFO, "x", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Sustituye secretos conocidos y patrones típicos de credenciales."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    for pattern in _PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
    return text


def _extras(record: logging.LogRecord) -> dict[str, object]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_ATTRS and not key.startswith("_")
    }


class TextFormatter(logging.Formatter):
    """`[2026-10-26, 10:15:03 UTC] {pipeline.py:61} INFO    - mensaje` (como Airflow)."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def format(self, record: logging.LogRecord) -> str:
        when = datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%d, %H:%M:%S UTC")
        line = (
            f"[{when}] {{{record.filename}:{record.lineno}}} "
            f"{record.levelname:<7} - {record.getMessage()}"
        )
        extras = _extras(record)
        if extras:
            line += "  (" + ", ".join(f"{k}={v}" for k, v in extras.items()) + ")"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return redact(line, self._secrets)


class JsonFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_extras(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, ensure_ascii=False, default=str), self._secrets)


def configure_logging(
    level: str = "INFO",
    secrets: Iterable[str] = (),
    stream: TextIO | None = None,
    fmt: str = "text",
) -> logging.Logger:
    """Configura el logger `etl_running` (`fmt`: `text` o `json`). Idempotente."""
    logger = logging.getLogger("etl_running")
    logger.setLevel(level.upper())
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter(secrets) if fmt == "json" else TextFormatter(secrets))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
