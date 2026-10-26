from __future__ import annotations

from etl_running.common.anonymize import (
    FAKE_ACTIVITY_NAME,
    FAKE_LAT,
    FAKE_LON,
    anonymize,
    find_pii,
)


def _raw_activity() -> dict:
    return {
        "activityId": 21000000001,
        "activityName": "Rodaje de Maria",
        "ownerId": 99887766,
        "ownerFullName": "Maria Perez",
        "ownerDisplayName": "maria-p",
        "ownerProfileImageUrlSmall": "https://example.invalid/a.png",
        "locationName": "Ciudad Real",
        "startLatitude": 40.4168,
        "startLongitude": -3.7038,
        "contacto": "maria@example.com",
        "distance": 10000.0,
        "nested": [{"endLatitude": 40.5, "endLongitude": -3.6}],
    }


def test_find_pii_detects_real_looking_data():
    paths = find_pii(_raw_activity())
    assert "$.ownerFullName" in paths
    assert "$.startLatitude" in paths
    assert "$.nested[0].endLongitude" in paths
    assert "$.contacto" in paths


def test_anonymize_removes_all_pii_and_keeps_shape():
    raw = _raw_activity()
    clean = anonymize(raw)
    assert find_pii(clean) == []
    assert clean["ownerFullName"] is None
    assert clean["ownerProfileImageUrlSmall"] is None
    assert clean["locationName"] is None
    assert clean["activityName"] == FAKE_ACTIVITY_NAME
    assert clean["startLatitude"] == FAKE_LAT
    assert clean["startLongitude"] == FAKE_LON
    assert clean["nested"][0]["endLatitude"] == FAKE_LAT
    assert clean["distance"] == 10000.0
    assert clean["contacto"] == "[email]"
    assert set(clean) == set(raw)


def test_anonymize_is_deterministic_and_does_not_mutate_input():
    raw = _raw_activity()
    snapshot = _raw_activity()
    first = anonymize(raw)
    second = anonymize(raw)
    assert first == second
    assert raw == snapshot
    assert first["activityId"] != raw["activityId"]


def test_salt_changes_ids():
    raw = _raw_activity()
    assert anonymize(raw, salt="a")["activityId"] != anonymize(raw, salt="b")["activityId"]


def test_null_values_stay_null():
    clean = anonymize({"startLatitude": None, "ownerFullName": None, "averageHR": None})
    assert clean == {"startLatitude": None, "ownerFullName": None, "averageHR": None}
