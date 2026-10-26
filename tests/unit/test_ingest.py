from __future__ import annotations

import copy
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from tests.unit.fakes import FakeClient, FakeHttpError

from etl_running.bronze.report import build_report, format_report
from etl_running.bronze.writer import BronzeWriter
from etl_running.common.config import DateOutsideWindowError, Settings
from etl_running.common.logging import configure_logging
from etl_running.ingest.cursor import CursorStore
from etl_running.ingest.extractors import extract_activities
from etl_running.ingest.garmin_client import IngestError, ResilientClient
from etl_running.ingest.pipeline import (
    CURSOR_KEY,
    WindowError,
    resolve_window,
    run_ingest,
    runs_log_path,
)

START = date(2026, 8, 17)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(lake_dir=tmp_path / "lake")


@pytest.fixture
def acts(activities_fixture) -> list[dict]:
    return activities_fixture


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def make_resilient(inner, **kw):
    sleeps: list[float] = []
    client = ResilientClient(
        inner, sleep=sleeps.append, min_interval=0, jitter=lambda: 0.0, base_delay=1.0, **kw
    )
    return client, sleeps


# ---- cliente resiliente ----------------------------------------------------


def test_retries_429_and_5xx_with_exponential_backoff(acts):
    client, sleeps = make_resilient(FakeClient(acts, failures=[429, 500, 503]))
    assert client.search_activities(start=0, limit=50)
    assert sleeps == [1.0, 2.0, 4.0]


def test_gives_up_after_max_retries(acts):
    client, _ = make_resilient(FakeClient(acts, failures=[500] * 10), max_retries=2)
    with pytest.raises(FakeHttpError):
        client.search_activities(start=0, limit=50)


def test_401_refreshes_token_once(acts):
    refreshed = []
    client, _ = make_resilient(
        FakeClient(acts, failures=[401]), refresh_token=lambda: refreshed.append(1)
    )
    assert client.search_activities(start=0, limit=50)
    assert refreshed == [1]


def test_persistent_401_fails_after_a_single_refresh(acts):
    refreshed = []
    client, _ = make_resilient(
        FakeClient(acts, failures=[401, 401]), refresh_token=lambda: refreshed.append(1)
    )
    with pytest.raises(FakeHttpError):
        client.search_activities(start=0, limit=50)
    assert refreshed == [1]


def test_non_retryable_error_is_raised_immediately(acts):
    client, sleeps = make_resilient(FakeClient(acts, failures=[403]))
    with pytest.raises(FakeHttpError):
        client.search_activities(start=0, limit=50)
    assert sleeps == []


def test_unexpected_response_shape_is_an_error():
    class Weird:
        def search_activities(self, **_):
            return {"oops": 1}

    client, _ = make_resilient(Weird())
    with pytest.raises(IngestError):
        client.search_activities(start=0, limit=50)


def test_min_interval_throttles_requests(acts):
    now = [0.0]
    sleeps: list[float] = []
    client = ResilientClient(
        FakeClient(acts), sleep=sleeps.append, clock=lambda: now[0], min_interval=0.5
    )
    client.search_activities(start=0, limit=50)
    client.search_activities(start=0, limit=50)
    assert sleeps == [0.5]


# ---- extractor -------------------------------------------------------------


def test_extractor_filters_window_and_keeps_all_types(acts):
    got = extract_activities(FakeClient(acts), START, date(2026, 12, 31))
    assert len(got) == len(acts)
    assert {a["activityType"]["typeKey"] for a in got} >= {"running", "cycling"}


def test_extractor_discards_activities_before_since(acts):
    old = copy.deepcopy(acts[0])
    old["activityId"] = 1
    old["startTimeLocal"] = "2026-08-01 07:00:00"
    got = extract_activities(FakeClient([*acts, old]), START, date(2026, 12, 31))
    assert 1 not in {a["activityId"] for a in got}


def test_extractor_paginates_and_dedupes(acts):
    many = []
    for i in range(7):
        a = copy.deepcopy(acts[0])
        a["activityId"] = 1000 + i
        a["startTimeLocal"] = f"2026-09-{10 + i:02d} 07:00:00"
        many.append(a)
    client = FakeClient(many)
    got = extract_activities(client, START, date(2026, 12, 31), page_size=3)
    assert [a["activityId"] for a in got] == [1000 + i for i in range(7)]
    assert client.calls == 3

    dup_client = FakeClient([*many, many[0]])
    assert len(extract_activities(dup_client, START, date(2026, 12, 31), page_size=3)) == 7


def test_extractor_stops_after_crossing_since(acts):
    old = []
    for i in range(10):
        a = copy.deepcopy(acts[0])
        a["activityId"] = 2000 + i
        a["startTimeLocal"] = f"2026-08-{i + 1:02d} 07:00:00"
        old.append(a)
    client = FakeClient([*acts, *old])
    extract_activities(client, START, date(2026, 12, 31), page_size=len(acts))
    assert client.calls == 2


# ---- escritura y bronze ----------------------------------------------------


def test_run_ingest_writes_one_partition_per_day_and_empty_days(settings, acts):
    until = date(2026, 10, 21)
    summary = run_ingest(settings, FakeClient(acts), START, until)
    assert summary.fetched == len(acts)
    assert summary.files_written == summary.days == (until - START).days + 1
    empty = list((settings.bronze_dir / "garmin/activities_list/dt=2026-08-17").glob("*.json"))
    assert json.loads(empty[0].read_text()) == []


def test_reconciliation_bronze_equals_api(settings, acts):
    summary = run_ingest(settings, FakeClient(acts), START, date(2026, 10, 21))
    (report,) = build_report(settings.bronze_dir, runs_log_path(settings.lake_dir))
    assert report.rows == summary.fetched == sum(report.type_counts.values())
    assert report.min_dt >= START


def test_second_run_creates_no_files_and_keeps_manifest(settings, acts):
    until = date(2026, 10, 21)
    run_ingest(settings, FakeClient(acts), START, until)
    before = snapshot(settings.bronze_dir)
    summary = run_ingest(settings, FakeClient(acts), START, until)
    assert summary.files_written == 0
    assert snapshot(settings.bronze_dir) == before


def test_bronze_files_are_never_modified(settings, acts):
    until = date(2026, 10, 21)
    run_ingest(settings, FakeClient(acts), START, until)
    before = snapshot(settings.bronze_dir)
    changed = copy.deepcopy(acts)
    changed[0]["distance"] = 12345.0
    summary = run_ingest(settings, FakeClient(changed), START, until)
    assert summary.files_written == 1
    after = snapshot(settings.bronze_dir)
    for path, digest in before.items():
        if not path.endswith("_manifest.parquet"):
            assert after[path] == digest
    assert len(after) == len(before) + 1


def test_writer_refuses_to_overwrite(settings):
    writer = BronzeWriter(settings.bronze_dir)
    writer.write_partition("garmin", "x", START, [{"activityId": 1}], "run1")
    with pytest.raises(FileExistsError):
        writer.write_partition("garmin", "x", START, [{"activityId": 2}], "run1")


def test_same_payload_in_any_order_has_same_hash(settings):
    writer = BronzeWriter(settings.bronze_dir)
    a, b = {"activityId": 1, "x": 1}, {"activityId": 2, "x": 2}
    assert writer.write_partition("garmin", "x", START, [a, b], "r1").written
    assert not writer.write_partition("garmin", "x", START, [b, a], "r2").written


def test_no_temp_files_left_behind(settings, acts):
    run_ingest(settings, FakeClient(acts), START, date(2026, 10, 21))
    assert not list(settings.lake_dir.rglob("*.tmp"))


# ---- cursor, ventana y reanudación -----------------------------------------


def test_cursor_roundtrip_and_never_regresses(settings, acts):
    run_ingest(settings, FakeClient(acts), START, date(2026, 10, 21))
    cursor = CursorStore(settings.lake_dir)
    assert cursor.get(CURSOR_KEY) == date(2026, 10, 21)
    run_ingest(settings, FakeClient(acts), START, date(2026, 9, 1))
    assert cursor.get(CURSOR_KEY) == date(2026, 10, 21)


def test_interrupted_backfill_resumes_to_same_result(settings, tmp_path, acts):
    until = date(2026, 10, 21)
    run_ingest(settings, FakeClient(acts), START, until)
    continuous = {p: h for p, h in snapshot(settings.bronze_dir).items() if p.endswith(".json")}

    other = Settings(lake_dir=tmp_path / "lake2")
    run_ingest(other, FakeClient(acts), START, date(2026, 9, 14))
    since, end = resolve_window(other, since=None, until=None, lookback=3, resume=True, today=until)
    assert since == date(2026, 9, 14)
    run_ingest(other, FakeClient(acts), since, end)

    def payloads(s: Settings) -> dict[str, list]:
        out = {}
        for p in sorted(s.bronze_dir.rglob("*.json")):
            out[p.parent.name] = json.loads(p.read_text())
        return out

    assert payloads(other) == payloads(settings)
    assert len(continuous) == len(list(other.bronze_dir.rglob("*.json")))


def test_failed_run_does_not_advance_cursor_and_is_reported(settings, acts):
    with pytest.raises(FakeHttpError):
        run_ingest(settings, FakeClient(acts, failures=[403]), START, date(2026, 10, 21))
    assert CursorStore(settings.lake_dir).get(CURSOR_KEY) is None
    (report,) = build_report(settings.bronze_dir, runs_log_path(settings.lake_dir))
    assert report.errors == 1


def test_window_rejects_dates_before_start(settings):
    today = date(2026, 10, 26)
    with pytest.raises(DateOutsideWindowError):
        resolve_window(
            settings, since=date(2026, 8, 1), until=None, lookback=3, resume=True, today=today
        )
    with pytest.raises(DateOutsideWindowError):
        resolve_window(
            settings, since=START, until=date(2026, 8, 1), lookback=3, resume=False, today=today
        )


def test_window_defaults_and_lookback(settings, acts):
    today = date(2026, 10, 26)
    assert resolve_window(
        settings, since="last", until=None, lookback=3, resume=False, today=today
    ) == (START, today)
    run_ingest(settings, FakeClient(acts), START, date(2026, 10, 21))
    assert resolve_window(
        settings, since="last", until=None, lookback=3, resume=False, today=today
    ) == (date(2026, 10, 19), today)


def test_window_rejects_inverted_range(settings):
    with pytest.raises(WindowError):
        resolve_window(
            settings,
            since=date(2026, 10, 5),
            until=date(2026, 10, 1),
            lookback=3,
            resume=False,
            today=date(2026, 10, 26),
        )


# ---- informe y logs --------------------------------------------------------


def test_report_breakdown_marks_scope(settings, acts):
    run_ingest(settings, FakeClient(acts), START, date(2026, 10, 21))
    reports = build_report(settings.bronze_dir, runs_log_path(settings.lake_dir))
    text = format_report(reports, settings.running_type_keys, today=date(2026, 10, 26))
    assert "garmin/activities_list" in text
    assert "out_of_scope" in text
    assert "running" in text


def test_report_on_empty_bronze(settings):
    assert "vacío" in format_report([], settings.running_type_keys)


def test_logs_do_not_leak_secrets(settings, acts, capsys):
    import io

    stream = io.StringIO()
    configure_logging("DEBUG", ["super-secret-key"], stream)
    client, _ = make_resilient(FakeClient(acts, failures=[500]))
    import logging

    logging.getLogger("etl_running").warning("key=super-secret-key Bearer abc.def.ghi")
    client.search_activities(start=0, limit=50)
    run_ingest(settings, FakeClient(acts), START, date(2026, 8, 20))
    out = stream.getvalue()
    assert "super-secret-key" not in out
    assert "abc.def.ghi" not in out
    assert "Synthetic" not in out


def test_partial_window_does_not_advance_cursor(settings, acts):
    run_ingest(settings, FakeClient(acts), date(2026, 10, 20), date(2026, 10, 26))
    assert CursorStore(settings.lake_dir).get(CURSOR_KEY) is None
    run_ingest(settings, FakeClient(acts), START, date(2026, 10, 26))
    assert CursorStore(settings.lake_dir).get(CURSOR_KEY) == date(2026, 10, 26)


def test_gap_after_cursor_does_not_advance_it(settings, acts):
    run_ingest(settings, FakeClient(acts), START, date(2026, 9, 1))
    run_ingest(settings, FakeClient(acts), date(2026, 10, 1), date(2026, 10, 5))
    assert CursorStore(settings.lake_dir).get(CURSOR_KEY) == date(2026, 9, 1)
    run_ingest(settings, FakeClient(acts), date(2026, 9, 2), date(2026, 9, 10))
    assert CursorStore(settings.lake_dir).get(CURSOR_KEY) == date(2026, 9, 10)


def test_latest_activities_and_format(settings, acts):
    from etl_running.bronze.report import format_activities, latest_activities

    run_ingest(settings, FakeClient(acts), START, date(2026, 10, 21))
    got = latest_activities(settings.bronze_dir, date(2026, 10, 1))
    assert got and all(a["startTimeLocal"][:10] >= "2026-10-01" for a in got)
    text = format_activities(got, settings.running_type_keys)
    assert "ritmo/km" in text
    assert "out_of_scope" in text
    assert "Sin actividades" in format_activities([], settings.running_type_keys)
