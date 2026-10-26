"""Anonimización de payloads de Garmin y detección de datos personales.

Se usa para convertir respuestas reales en fixtures seguros y para comprobar que
ningún fixture versionado contiene nombres, URLs de perfil ni coordenadas reales.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

FAKE_LAT = 0.0
FAKE_LON = 0.0
FAKE_COORD_TOLERANCE = 0.1

NULLED_KEYS = frozenset(
    {
        "ownerFullName",
        "ownerDisplayName",
        "ownerProfileImageUrlSmall",
        "ownerProfileImageUrlMedium",
        "ownerProfileImageUrlLarge",
        "locationName",
    }
)
FAKE_OWNER_ID = 1
FAKE_ACTIVITY_NAME = "Synthetic activity"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
FAKE_EMAIL = "[email]"


def _is_coord_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.endswith(("latitude", "longitude"))


def _fake_activity_id(value: int, salt: str) -> int:
    digest = hashlib.sha256(f"{salt}:{value}".encode()).digest()
    return 1_000_000_000 + int.from_bytes(digest[:6], "big") % 9_000_000_000


def anonymize(obj: Any, salt: str = "etl-running") -> Any:
    """Devuelve una copia sin datos personales; conserva la forma del payload."""
    if isinstance(obj, list):
        return [anonymize(item, salt) for item in obj]
    if isinstance(obj, str):
        return _EMAIL.sub(FAKE_EMAIL, obj)
    if not isinstance(obj, dict):
        return obj

    clean: dict[str, Any] = {}
    for key, value in obj.items():
        if key in NULLED_KEYS:
            clean[key] = None
        elif key == "ownerId" and value is not None:
            clean[key] = FAKE_OWNER_ID
        elif key == "activityName" and value is not None:
            clean[key] = FAKE_ACTIVITY_NAME
        elif key == "activityId" and isinstance(value, int):
            clean[key] = _fake_activity_id(value, salt)
        elif _is_coord_key(key) and isinstance(value, int | float):
            clean[key] = FAKE_LAT if key.lower().endswith("latitude") else FAKE_LON
        else:
            clean[key] = anonymize(value, salt)
    return clean


def find_pii(obj: Any, path: str = "$") -> list[str]:
    """Lista las rutas que parecen contener datos personales (vacía si está limpio)."""
    found: list[str] = []
    if isinstance(obj, list):
        for index, item in enumerate(obj):
            found.extend(find_pii(item, f"{path}[{index}]"))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}"
            if key in NULLED_KEYS and value is not None:
                found.append(here)
            elif _is_coord_key(key) and isinstance(value, int | float):
                if abs(value) > FAKE_COORD_TOLERANCE:
                    found.append(here)
            else:
                found.extend(find_pii(value, here))
    elif isinstance(obj, str) and _EMAIL.search(obj):
        found.append(path)
    return found
