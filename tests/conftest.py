from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def activities_fixture() -> list[dict]:
    return json.loads((FIXTURES / "garmin" / "activities_list.json").read_text(encoding="utf-8"))
