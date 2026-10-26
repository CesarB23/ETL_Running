from __future__ import annotations

import io
import json
import logging

from etl_running.common.logging import REDACTED, configure_logging, redact

SECRET = "super-secret-key-123"


def test_redact_known_secret():
    assert SECRET not in redact(f"clave {SECRET} usada", secrets=[SECRET])


def test_redact_bearer_and_key_value_patterns():
    assert redact("Authorization: Bearer abc.def-123") == f"Authorization: Bearer {REDACTED}"
    assert "xyz" not in redact("api_key=xyz")
    assert "xyz" not in redact("password: xyz")
    assert "xyz" not in redact('{"token": "xyz"}')


def test_json_log_is_valid_and_redacted():
    stream = io.StringIO()
    logger = configure_logging("INFO", secrets=[SECRET], stream=stream, fmt="json")
    logger.info("llamando con %s", SECRET, extra={"dataset": "activities_list", "n": 3})
    line = stream.getvalue().strip()
    assert SECRET not in line
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["dataset"] == "activities_list"
    assert payload["n"] == 3
    assert REDACTED in payload["message"]


def test_extras_are_redacted_too():
    stream = io.StringIO()
    logger = configure_logging("INFO", secrets=[SECRET], stream=stream, fmt="json")
    logger.warning("fallo", extra={"detail": f"token={SECRET}"})
    assert SECRET not in stream.getvalue()


def test_configure_logging_is_idempotent():
    configure_logging("INFO", stream=io.StringIO())
    logger = configure_logging("DEBUG", stream=io.StringIO())
    assert len(logger.handlers) == 1
    assert logger.level == logging.DEBUG


def test_text_format_is_airflow_like_and_redacted():
    import re

    stream = io.StringIO()
    logger = configure_logging("INFO", secrets=[SECRET], stream=stream)
    logger.info("Paso 1/3 · usando %s", SECRET)
    line = stream.getvalue().strip()
    assert SECRET not in line
    assert re.match(
        r"^\[\d{4}-\d\d-\d\d, \d\d:\d\d:\d\d UTC\] \{test_logging\.py:\d+\} INFO    - Paso 1/3",
        line,
    )


def test_text_format_shows_extras_and_traceback():
    stream = io.StringIO()
    logger = configure_logging("INFO", stream=stream)
    try:
        raise ValueError("boom")
    except ValueError:
        logger.error("falló", extra={"dataset": "x"}, exc_info=True)
    out = stream.getvalue()
    assert "(dataset=x)" in out
    assert "ValueError: boom" in out
