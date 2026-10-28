#!/bin/zsh
# Ejecuta el pipeline diario desde launchd manteniendo el Mac despierto.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$PROJECT_DIR/lake/_state"
cd "$PROJECT_DIR"

# launchd no hereda el PATH de una terminal interactiva; uv suele instalarse aquí.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

# -d/-i/-m/-s evitan dormir pantalla, sistema, disco y CPU mientras corre el job.
# -u declara actividad de usuario; launchd no tiene sesión interactiva.
exec /usr/bin/caffeinate -dimsu /usr/bin/make run-daily
