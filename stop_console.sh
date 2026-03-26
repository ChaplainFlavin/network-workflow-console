#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
PID_FILE="$PROJECT_DIR/data/server.pid"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" | tr -d '[:space:]')"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    sleep 0.5
  fi
fi

if lsof -nP -iTCP:8123 -sTCP:LISTEN >/dev/null 2>&1; then
  lsof -nP -iTCP:8123 -sTCP:LISTEN | awk 'NR>1 {print $2}' | xargs -r kill
fi

rm -f "$PID_FILE"
