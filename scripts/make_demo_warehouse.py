#!/usr/bin/env python
"""Crea un warehouse sintético para probar el dashboard sin datos personales."""

from __future__ import annotations

import argparse
from pathlib import Path

from etl_running.demo.warehouse import build_demo_warehouse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("lake_demo/warehouse.duckdb"),
        help="Ruta del DuckDB de demo (por defecto: lake_demo/warehouse.duckdb).",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    target = build_demo_warehouse(args.out, seed=args.seed)
    print(f"Warehouse demo: {target}")
    print("Activa el modo demo con DEMO_MODE=1 y ejecuta `make app`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
