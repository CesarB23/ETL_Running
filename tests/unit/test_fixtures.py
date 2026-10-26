from __future__ import annotations

import json
from pathlib import Path

import pytest

from etl_running.common.anonymize import find_pii

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _json_fixtures() -> list[Path]:
    return sorted(FIXTURES.rglob("*.json"))


@pytest.mark.parametrize("path", _json_fixtures(), ids=lambda p: str(p.relative_to(FIXTURES)))
def test_fixtures_contain_no_personal_data(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert find_pii(data) == []


def test_there_is_at_least_one_fixture():
    assert _json_fixtures()


def test_activities_fixture_covers_expected_cases(activities_fixture):
    assert len(activities_fixture) == 5
    ids = [a["activityId"] for a in activities_fixture]
    assert len(set(ids)) == 5

    by_type = [a["activityType"]["typeKey"] for a in activities_fixture]
    assert by_type.count("running") == 3
    assert "cycling" in by_type
    assert "other" in by_type

    running = [a for a in activities_fixture if a["activityType"]["typeKey"] == "running"]
    assert any(a["manualActivity"] for a in running)
    assert any(a["averageHR"] is None and not a["manualActivity"] for a in running)
    assert any(a["averageHR"] is not None for a in running)


def test_activities_fixture_is_inside_the_window(activities_fixture):
    assert min(a["startTimeLocal"] for a in activities_fixture) >= "2026-08-17"
