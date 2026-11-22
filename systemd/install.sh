#!/bin/bash
# MediaForge を systemd の user unit として入れる / 外す
#   ./systemd/install.sh            入れて起動（enable --now）
#   ./systemd/install.sh uninstall  止めて外す
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/mediaforge.service"

if [ "${1:-install}" = "uninstall" ]; then
  systemctl --user disable --now mediaforge.service 2>/dev/null || true
  rm -f "$UNIT"
  systemctl --user daemon-reload
  echo "removed $UNIT"
  exit 0
fi

# .venv が無ければ作る（run.sh と同じ）
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  python3 -m venv "$APP_DIR/.venv"
  "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.lock"
fi

mkdir -p "$UNIT_DIR"
sed "s|@APP_DIR@|$APP_DIR|g" "$APP_DIR/systemd/mediaforge.service" > "$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now mediaforge.service
echo "installed $UNIT"
systemctl --user --no-pager status mediaforge.service | head -5
echo "ログアウト後も動かす場合: sudo loginctl enable-linger $USER"
