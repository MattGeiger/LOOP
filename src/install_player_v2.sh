#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Install display player v2 on a LOOP display Pi. Run as the desktop user (no sudo needed).
# Requires the USB data drive mounted at /mnt/loopdata (see setup_usb.sh).
#  - ~/loop/display_player.py + config.json (drop folder /mnt/loopdata/videos)
#  - ~/loop/idle.png  (branded idle image; the pre-rotated one on a portrait display)
#  - ~/loop/backup.mp4 on the SD card, used if the USB drive or its videos are missing
#  - seeds the drop folder with the current video if it is empty
#  - moves burn-in logging to /mnt/loopdata/logs (old logs copied, originals kept)
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
DATA="$(python3 "$SRC/loop_profile.py" get system.data_mount)"
KEEP="$(python3 "$SRC/loop_profile.py" get content.keep_videos)"
APP="$HOME/loop"

mountpoint -q "$DATA" || { echo "ABORT: $DATA is not mounted"; exit 1; }
mkdir -p "$APP" "$DATA/videos" "$DATA/state" "$DATA/logs"

# Player + settings
install -m 755 "$SRC/display_player.py" "$APP/display_player.py"
install -m 644 "$SRC/loop_profile.py" "$APP/"
for f in profile.json site.json; do  # organization profile and this deployment's private settings
  if [ -f "$SRC/$f" ]; then install -m 644 "$SRC/$f" "$APP/$f"; fi
done
cat > "$APP/config.json" <<EOF
{
  "videos_dir": "$DATA/videos",
  "state_dir": "$DATA/state",
  "log_dir": "$DATA/logs",
  "backup_video": "$APP/backup.mp4",
  "idle_image": "$APP/idle.png",
  "keep": $KEEP
}
EOF

# Idle image: a display mounted portrait (site.json displays.<hostname>.orientation = portrait-cw)
# gets the pre-rotated art. The MP4 is preferred by the player (hardware decoded); PNG is the fallback.
case "$(python3 "$SRC/loop_profile.py" orientation)" in
  portrait-cw) SUFFIX="-rotated" ;;
  *)           SUFFIX="" ;;
esac
install -m 644 "$SRC/idle-screen$SUFFIX.png" "$APP/idle.png"
[ -f "$SRC/idle-screen$SUFFIX.mp4" ] && install -m 644 "$SRC/idle-screen$SUFFIX.mp4" "$APP/idle.mp4"

# Current video (from player v1) becomes the SD backup and the first drop-folder video.
CUR="$(cat "$HOME/.config/loop/last-media" 2>/dev/null || true)"
if [ -n "$CUR" ] && [ -f "$CUR" ]; then
  [ -f "$APP/backup.mp4" ] || cp "$CUR" "$APP/backup.mp4"
  if [ -z "$(ls -A "$DATA/videos")" ]; then cp "$CUR" "$DATA/videos/"; fi
fi
echo "Backup video: $(ls -l "$APP/backup.mp4" 2>/dev/null | awk '{print $5" bytes"}' || echo none)"
echo "Drop folder:"; ls -l "$DATA/videos"

# Burn-in logs move to the USB drive.
cp -n "$HOME"/burnin/logs/*.csv "$DATA/logs/" 2>/dev/null || true
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/burnin-logger.service" <<EOF
[Unit]
Description=Display burn-in logger (temps, memory, VLC frame drops)
After=local-fs.target

[Service]
Environment=BURNIN_LOG_DIR=$DATA/logs
# Performance History retention: 168 h (7 days) during burn-in; set to 24 at go-live.
Environment=BURNIN_KEEP_HOURS=168
ExecStart=/usr/bin/python3 %h/burnin/burnin_logger.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user restart burnin-logger.service
systemctl --user restart display-player.service

sleep 25
echo "--- status"
systemctl --user is-active display-player burnin-logger
cat "$DATA/state/status.json" 2>/dev/null || echo "no status yet"
tail -n 3 "$DATA/logs/player.log" 2>/dev/null
echo PLAYER_V2_DONE
