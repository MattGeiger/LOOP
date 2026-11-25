#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Install the zero-touch player on a display Pi. Run as the desktop user (no sudo needed).
#   bash install_autostart.sh            # remembers the video VLC is playing now
#   bash install_autostart.sh /path.mp4  # or start with a specific file
# Installs ~/loop/display_player.py and the user service display-player.service
# (enabled at boot via lingering + desktop auto-login), then hands VLC over to it.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
STATE="$HOME/.config/loop/last-media"

# --- remember the current video ----------------------------------------------
MEDIA="${1:-}"
VLCPID="$(pgrep -o -x vlc || true)"
if [ -z "$MEDIA" ] && [ -n "$VLCPID" ]; then
  MEDIA="$(tr '\0' '\n' < /proc/$VLCPID/cmdline | grep -E '^(file://|/home)' | tail -1)"
fi
if [ -n "$MEDIA" ]; then
  MEDIA="$(python3 -c 'import sys,urllib.parse as u; m=sys.argv[1]; print(u.unquote(u.urlparse(m).path) if m.startswith("file://") else m)' "$MEDIA")"
  [ -f "$MEDIA" ] || { echo "Not a file: $MEDIA"; exit 1; }
  mkdir -p "$(dirname "$STATE")"
  echo "$MEDIA" > "$STATE"
fi
echo "Last media: $(cat "$STATE" 2>/dev/null || echo '(none; newest video in ~/Videos or ~/Downloads will be used)')"

# --- install player + service ---------------------------------------------------
mkdir -p "$HOME/loop" "$HOME/.config/systemd/user"
install -m 755 "$SRC/display_player.py" "$HOME/loop/"
install -m 644 "$SRC/loop_profile.py" "$HOME/loop/"
for f in profile.json site.json; do  # organization profile and this deployment's private settings
  if [ -f "$SRC/$f" ]; then install -m 644 "$SRC/$f" "$HOME/loop/$f"; fi
done
cat > "$HOME/.config/systemd/user/display-player.service" <<'EOF'
[Unit]
Description=LOOP display: VLC fullscreen loop of the last video (zero-touch)

[Service]
ExecStart=/usr/bin/python3 %h/loop/display_player.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

# --- hand over from any manually started VLC -------------------------------------
systemctl --user stop burnin-vlc.service 2>/dev/null || true
if pgrep -x vlc >/dev/null; then
  pkill -TERM -x vlc || true
  for _ in $(seq 1 20); do pgrep -x vlc >/dev/null || break; sleep 0.5; done
  pkill -KILL -x vlc 2>/dev/null || true
fi
systemctl --user daemon-reload
systemctl --user enable display-player.service
systemctl --user restart display-player.service

sleep 20
echo "--- status"
systemctl --user is-enabled display-player.service
systemctl --user is-active display-player.service
pgrep -a -x vlc || echo "VLC NOT RUNNING"
journalctl --user -u display-player.service -n 3 --no-pager -o cat
echo "AUTOSTART_DONE"
