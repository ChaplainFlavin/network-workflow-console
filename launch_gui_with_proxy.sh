#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
PROFILE="${1:-}"
CODEX_APP="/Applications/Codex.app"
ANTIGRAVITY_APP="/Applications/Antigravity.app"

mapfile=("${(@f)$(/usr/bin/python3 "$PROJECT_DIR/gui_proxy_mode.py" "$PROFILE")}")
PROXY_URL="${mapfile[1]}"
NO_PROXY_VALUE="${mapfile[2]}"
BYPASS_LIST="${NO_PROXY_VALUE//,/;}"

launchctl setenv HTTP_PROXY "$PROXY_URL"
launchctl setenv HTTPS_PROXY "$PROXY_URL"
launchctl setenv ALL_PROXY "$PROXY_URL"
launchctl setenv NO_PROXY "$NO_PROXY_VALUE"

osascript <<EOF >/dev/null
tell application "Codex" to quit
tell application "Antigravity" to quit
delay 1
EOF

open -na "$CODEX_APP" --args "--proxy-server=$PROXY_URL" "--proxy-bypass-list=$BYPASS_LIST"
open -na "$ANTIGRAVITY_APP" --args "--proxy-server=$PROXY_URL" "--proxy-bypass-list=$BYPASS_LIST"
