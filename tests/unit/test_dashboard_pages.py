from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from etl_running.demo.warehouse import build_demo_warehouse

ROOT = Path(__file__).resolve().parents[2]
PAGES = [
    "main.py",
    "pages/0_Resumen.py",
    "pages/1_Progreso.py",
    "pages/2_Carga.py",
    "pages/3_Plan_vs_real.py",
    "pages/4_Salud_pipeline.py",
]


def test_all_pages_render_with_demo_warehouse(monkeypatch, tmp_path: Path):
    build_demo_warehouse(tmp_path / "warehouse.duckdb")
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_LAKE_DIR", str(tmp_path))
    for page in PAGES:
        app = AppTest.from_file(str(ROOT / "app" / page), default_timeout=20).run()
        assert not app.exception, f"{page}: {[exc.value for exc in app.exception]}"
