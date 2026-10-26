#!/usr/bin/env python3
"""Anonimiza un JSON de Garmin para poder usarlo como fixture.

Uso:
    uv run python scripts/anonymize.py entrada.json salida.json

Elimina nombres y URLs de perfil, sustituye coordenadas por un punto ficticio y
reasigna los `activityId`. Nunca versiones el archivo de entrada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from etl_running.common.anonymize import anonymize, find_pii


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--salt", default="etl-running", help="Sal para reasignar IDs.")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    clean = anonymize(data, salt=args.salt)

    leftovers = find_pii(clean)
    if leftovers:
        print("Quedan datos personales sin anonimizar:", file=sys.stderr)
        for path in leftovers:
            print(f"  {path}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Escrito {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
