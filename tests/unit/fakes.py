"""Cliente falso de Garmin para tests (sin red)."""

from __future__ import annotations

import copy
from typing import Any


class FakeHttpError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FakeClient:
    """Sirve `activities` paginadas; `failures` es una cola de códigos HTTP a lanzar."""

    def __init__(self, activities: list[dict[str, Any]], failures: list[int] | None = None):
        self.activities = sorted(
            copy.deepcopy(activities), key=lambda a: a["startTimeLocal"], reverse=True
        )
        self.failures = list(failures or [])
        self.calls = 0

    def search_activities(self, *, start: int, limit: int) -> list[dict[str, Any]]:
        self.calls += 1
        if self.failures:
            raise FakeHttpError(self.failures.pop(0))
        return copy.deepcopy(self.activities[start : start + limit])
