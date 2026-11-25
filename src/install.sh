#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Install the burn-in logger on a display Pi. Run as the desktop user (no sudo needed).
#   bash install.sh            # uses the file VLC is currently playing
#   bash install.sh /path.mp4  # or a specific file
# What it does:
#   1. Copies the logger + summary into ~/burnin and installs a user systemd service.
#   2. Enables VLC's HTTP interface on 127.0.0.1:8080 (random password) and loop=1 in vlcrc
#      (backup kept as vlcrc.bak-burnin-<timestamp>).
#   3. Restarts VLC fullscreen + looping so the HTTP interface is active.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
VLCRC="$HOME/.config/vlc/vlcrc"

# --- media to play ---------------------------------------------------------
MEDIA="${1:-}"
VLCPID="$(pgrep -o -x vlc || true)"
if [ -z "$MEDIA" ] && [ -n "$VLCPID" ]; then
  MEDIA="$(tr '\0' '\n' < /proc/$VLCPID/cmdline | grep -E '^(file://|/)' | tail -1)"
fi
[ -n "$MEDIA" ] || { echo "No media file found; pass one as an argument."; exit 1; }
echo "Media: $MEDIA"

# --- logger files + service ------------------------------------------------
mkdir -p "$HOME/burnin/logs" "$HOME/.config/systemd/user"
if [ "$SRC" != "$HOME/burnin" ]; then
  install -m 755 "$SRC/burnin_logger.py" "$SRC/burnin_summary.py" "$HOME/burnin/"
fi
cat > "$HOME/.config/systemd/user/burnin-logger.service" <<'EOF'
[Unit]
Description=Display burn-in logger (temps, memory, VLC frame drops)

[Service]
ExecStart=/usr/bin/python3 %h/burnin/burnin_logger.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

# --- stop VLC before editing its config -------------------------------------
systemctl --user stop burnin-vlc.service 2>/dev/null || true
if pgrep -x vlc >/dev/null; then
  pkill -TERM -x vlc || true
  for _ in $(seq 1 20); do pgrep -x vlc >/dev/null || break; sleep 0.5; done
  pkill -KILL -x vlc 2>/dev/null || true
fi

# --- vlcrc: HTTP interface on localhost + loop -------------------------------
mkdir -p "$(dirname "$VLCRC")"
if [ -s "$VLCRC" ]; then
  cp -p "$VLCRC" "$VLCRC.bak-burnin-$(date +%Y%m%d-%H%M%S)"
else
  : > "$VLCRC"  # fresh system: VLC has not written its settings yet; only LOOP's keys are needed
fi
PW="$(grep -m1 '^http-password=.' "$VLCRC" | cut -d= -f2- || true)"
[ -n "$PW" ] || PW="$(python3 -c 'import secrets; print(secrets.token_hex(12))')"
setkey() {  # setkey key value : replace first "#key=" or "key=" line
  if grep -qE "^#?$1=" "$VLCRC"; then
    sed -i -E "0,/^#?$1=.*/s||$1=$2|" "$VLCRC"
  else
    echo "$1=$2" >> "$VLCRC"
  fi
}
setkey extraintf http
setkey http-host 127.0.0.1
setkey http-port 8080
setkey http-password "$PW"
setkey loop 1
grep -E '^(extraintf|http-host|http-port|loop)=' "$VLCRC"

# --- start VLC + logger ------------------------------------------------------
if systemctl --user is-enabled display-player.service >/dev/null 2>&1; then
  systemctl --user restart display-player.service   # zero-touch player owns VLC
else
  systemd-run --user --unit=burnin-vlc --collect \
    -E WAYLAND_DISPLAY=wayland-0 -E DISPLAY=:0 -E XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    /usr/bin/vlc --fullscreen --loop --no-video-title-show "$MEDIA"
fi

systemctl --user daemon-reload
systemctl --user enable burnin-logger.service
systemctl --user restart burnin-logger.service

sleep 12
echo "--- VLC stats check"
curl -s -u ":$PW" http://127.0.0.1:8080/requests/status.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d.get("stats",{}); print("state", d.get("state"), "| displayed", s.get("displayedpictures"), "lost", s.get("lostpictures"), "decoded", s.get("decodedvideo"))'
echo "--- latest log rows"
tail -n 2 "$HOME/burnin/logs/burnin-$(date +%F).csv"
echo "INSTALL_DONE"
