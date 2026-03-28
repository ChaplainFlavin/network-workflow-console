#!/bin/zsh
set -euo pipefail

CODEX_APP="/Applications/Codex.app"
ANTIGRAVITY_APP="/Applications/Antigravity.app"

launchctl unsetenv HTTP_PROXY || true
launchctl unsetenv HTTPS_PROXY || true
launchctl unsetenv ALL_PROXY || true
launchctl unsetenv NO_PROXY || true

osascript <<EOF >/dev/null
tell application "Codex" to quit
tell application "Antigravity" to quit
delay 1
EOF

open -a "$CODEX_APP"
open -a "$ANTIGRAVITY_APP"
