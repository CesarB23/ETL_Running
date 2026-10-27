"""API local de solo lectura y servidor de la interfaz React compilada."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from app import queries

ROOT = Path(__file__).resolve().parent.parent
WEB_DIST = ROOT / "web" / "dist"


def _clean(value):
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _frame_records(frame: pd.DataFrame) -> list[dict]:
    return _clean(frame.to_dict(orient="records"))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIST), **kwargs)

    def _json(self, payload, status=200):
        body = json.dumps(_clean(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/activities":
                return self._json(_frame_records(queries.activities()))
            if path == "/api/summary":
                return self._json(
                    {
                        "snapshot": queries.latest_snapshot(),
                        "weekly": _frame_records(queries.weekly_summary()),
                    }
                )
            if path == "/api/progress":
                return self._json(_frame_records(queries.progress(days=180)))
            if path == "/api/load":
                return self._json(_frame_records(queries.training_load(days=120)))
            if path == "/api/health":
                return self._json(
                    {
                        "quality": _frame_records(queries.data_quality()),
                        "alerts": queries.alerts_tail(),
                        "snapshot": queries.latest_snapshot(),
                    }
                )
            if path.startswith("/api/activities/"):
                parts = path.strip("/").split("/")
                if len(parts) not in (3, 4):
                    return self._json({"error": "Ruta no encontrada"}, 404)
                activity_id = int(parts[2])
                section = parts[3] if len(parts) == 4 else "detail"
                loaders = {
                    "laps": queries.activity_laps,
                    "track": queries.activity_track,
                    "plan": queries.activity_plan,
                }
                if section == "detail":
                    activity = queries.activities(limit=100)
                    record = activity.loc[activity["activity_id"] == activity_id]
                    return self._json(_frame_records(record))
                if section not in loaders:
                    return self._json({"error": "Ruta no encontrada"}, 404)
                return self._json(_frame_records(loaders[section](activity_id)))
            if path.startswith("/api/"):
                return self._json({"error": "Ruta no encontrada"}, 404)
            if not WEB_DIST.is_dir():
                return self._json(
                    {"error": "Interfaz no compilada. Ejecuta `npm --prefix web run build`."},
                    503,
                )
            if path == "/":
                self.path = "/index.html"
            return super().do_GET()
        except (queries.DashboardError, ValueError) as exc:
            return self._json({"error": str(exc)}, 503)

    def log_message(self, fmt, *args):
        # Sin IDs, rutas ni datos deportivos en logs de acceso.
        return


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Dashboard local: http://localhost:8000", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
