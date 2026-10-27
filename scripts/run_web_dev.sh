#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
uv run python -m app.api &
api_pid=$!
cleanup() {
  kill "$api_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
npm --prefix web run dev
