#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Render the LOOP default profile artwork (TemplePDX.com branding) on macOS:
#   idle-screen.png / .mp4           1920x1080  landscape displays (also the desktop wallpaper)
#   idle-screen-portrait.png         1080x1920  design master for portrait displays
#   idle-screen-rotated.png / .mp4   1920x1080  portrait art turned 90 degrees clockwise
#   logo-white.png                   Staff Display Tools header logo (TemplePDX wordmark, white)
#   staff-icon.png                   256x256 taskbar and desktop icon
set -euo pipefail
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
shot() { "$CHROME" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
  --default-background-color=00000000 --window-size="$2" --screenshot="$PWD/$1.png" "file://$PWD/$1.html" >/dev/null 2>&1; }
shot idle-screen 1920,1080; shot idle-screen-portrait 1080,1920; shot staff-icon 256,256
sips -r 90 idle-screen-portrait.png --out idle-screen-rotated.png >/dev/null
python3 - <<'PY'
import pymupdf as f
d = f.open("wordmark-white.svg")  # white fill written in; the renderer ignores <style>
pg = d[0]; z = 1080 / pg.rect.width  # 3x, sharp up to 4K
pg.get_pixmap(matrix=f.Matrix(z, z), alpha=True).save("logo-white.png")
PY
for v in idle-screen idle-screen-rotated; do
  ffmpeg -y -loglevel error -loop 1 -framerate 2 -i "$v.png" -t 60 \
    -c:v libx264 -preset slow -tune stillimage -crf 18 -profile:v high -level 4.0 \
    -pix_fmt yuv420p -r 2 -movflags +faststart -an "$v.mp4"
done
ls -la *.png *.mp4
