#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="${HOME}/Desktop"
TARGET_DIR="${1:-$DESKTOP_DIR}"

mkdir -p "$TARGET_DIR"

cat >"$TARGET_DIR/网络工作流控制台.command" <<EOF
#!/bin/zsh
"$PROJECT_DIR/launch_console.sh"
osascript <<'APPLESCRIPT'
tell application "Terminal"
  repeat with w in windows
    try
      if name of w contains "网络工作流控制台.command" then
        close w saving no
      end if
    end try
  end repeat
end tell
APPLESCRIPT
EOF

cat >"$TARGET_DIR/关闭网络工作流控制台.command" <<EOF
#!/bin/zsh
"$PROJECT_DIR/stop_console.sh"
EOF

cat >"$TARGET_DIR/代理启动 Codex+Antigravity.command" <<EOF
#!/bin/zsh
"$PROJECT_DIR/launch_gui_with_proxy.sh"
EOF

cat >"$TARGET_DIR/恢复普通 Codex+Antigravity.command" <<EOF
#!/bin/zsh
"$PROJECT_DIR/clear_gui_proxy_env.sh"
EOF

chmod +x \
  "$TARGET_DIR/网络工作流控制台.command" \
  "$TARGET_DIR/关闭网络工作流控制台.command" \
  "$TARGET_DIR/代理启动 Codex+Antigravity.command" \
  "$TARGET_DIR/恢复普通 Codex+Antigravity.command"

echo "Shortcuts installed to: $TARGET_DIR"
