#!/bin/zsh
set -euo pipefail

launchctl unsetenv HTTP_PROXY || true
launchctl unsetenv HTTPS_PROXY || true
launchctl unsetenv ALL_PROXY || true
launchctl unsetenv NO_PROXY || true

osascript <<EOF >/dev/null
tell application "Codex" to quit
tell application "Antigravity" to quit
delay 1
tell application "Codex" to activate
tell application "Antigravity" to activate
EOF
