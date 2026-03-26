#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
URL="http://127.0.0.1:8123"
SERVER_CMD="printf '\\e]1;Network Workflow Console\\a'; printf '\\e]2;Network Workflow Console\\a'; cd '$PROJECT_DIR' && /usr/bin/python3 '$PROJECT_DIR/server.py'"

if ! curl --silent --fail "$URL/api/status" >/dev/null 2>&1; then
  osascript - "$SERVER_CMD" <<'EOF' >/dev/null
on run argv
  tell application "Terminal"
    do script (item 1 of argv)
  end tell
end run
EOF
  for _ in {1..20}; do
    if curl --silent --fail "$URL/api/status" >/dev/null 2>&1; then
      break
    fi
    sleep 0.4
  done
fi

open "$URL"
