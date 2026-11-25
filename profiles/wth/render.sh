#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Render the branded idle screen to PNGs with headless Chrome (macOS).
# The same design is used as the desktop wallpaper.
#   idle-screen.png           1920x1080  landscape display
#   idle-screen-portrait.png  1080x1920  design master for a portrait display
#   idle-screen-rotated.png  1920x1080  portrait art turned 90 degrees clockwise
# A portrait TV keeps the Pi output landscape, so its art is pre-rotated (portrait top at
# the right edge).
set -euo pipefail
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for page in idle-screen idle-screen-portrait; do
  case "$page" in *-portrait) size=1080,1920 ;; *) size=1920,1080 ;; esac
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
    --window-size="$size" --screenshot="$PWD/$page.png" "file://$PWD/$page.html" >/dev/null 2>&1
  echo "rendered $page.png ($size)"
done
sips -r 90 idle-screen-portrait.png --out idle-screen-rotated.png >/dev/null
echo "rotated idle-screen-rotated.png (1920x1080)"

# Idle screens as H.264 MP4 so the Pi plays them through its hardware decoder (a PNG goes
# through VLC's software path and costs far more CPU). The picture never changes, so 2 fps
# and 60 s long: tiny files, minimal redraw work, and rare loop restarts.
for f in idle-screen idle-screen-rotated; do
  ffmpeg -y -loglevel error -loop 1 -framerate 2 -i "$f.png" -t 60 \
    -c:v libx264 -preset slow -tune stillimage -crf 18 -profile:v high -level 4.0 \
    -pix_fmt yuv420p -r 2 -movflags +faststart -an "$f.mp4"
  echo "encoded $f.mp4"
done
