#!/bin/bash
# Instala/recarga el LaunchAgent diario de Dagster para el usuario actual.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.etl-running.daily"
TEMPLATE="$PROJECT_DIR/orchestration/launchd/$LABEL.plist"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "No existe $TEMPLATE" >&2
  exit 2
fi
if [[ ! -x "$PROJECT_DIR/scripts/run_daily.sh" ]]; then
  chmod +x "$PROJECT_DIR/scripts/run_daily.sh"
fi

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/lake/_state"
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$TEMPLATE" > "$DEST"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$DEST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "LaunchAgent instalado: $DEST"
echo "Horario: 20:00 local. Configura macOS en America/Mexico_City. Logs: $PROJECT_DIR/lake/_state/launchd.*.log"
echo "Desinstalar: launchctl bootout $DOMAIN/$LABEL && rm -f '$DEST'"
