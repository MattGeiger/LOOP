#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Build the LOOP image for Raspberry Pi Imager: the official Raspberry Pi OS (64-bit, with desktop) image with the
# loop-display package installed. Write it with Pi Imager (OS customisation works as usual: user, hostname, Wi-Fi,
# SSH); LOOP Setup opens at the first login.
#   packaging/build-pi-image.sh <raspios .img or .img.xz> [profile ...]     e.g.  ... raspios.img.xz wth
# Writes dist/loop-pios_<version>[+profiles]_arm64.img.xz, its .sha256, and a Pi Imager repository file
# (dist/loop-imager.json). Needs Docker (arm64; Apple silicon runs it natively).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:?official Raspberry Pi OS image (.img or .img.xz)}"; shift
SRC="$(cd "$(dirname "$SRC")" && pwd)/$(basename "$SRC")"
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$ROOT/src/staff_tools.py")"
SUFFIX="$( [ $# -gt 0 ] && echo "+$(IFS=+; echo "$*")" || true )"
DEB="$ROOT/dist/loop-display_${VERSION}${SUFFIX}_all.deb"
[ -f "$DEB" ] || "$ROOT/packaging/build-deb.sh" "$@"
NAME="loop-pios_${VERSION}${SUFFIX}_arm64"
W="$ROOT/dist/image-build"; rm -rf "$W"; mkdir -p "$W"
case "$SRC" in *.xz) xz -dc "$SRC" > "$W/base.img" ;; *) cp "$SRC" "$W/base.img" ;; esac
cp "$DEB" "$W/loop.deb"
docker run --rm --privileged --platform linux/arm64 -v "$W":/w -v "$ROOT/packaging/image":/s:ro debian:trixie-slim \
  bash /s/inside.sh | tee "$W/build.log"
grep -q IMAGE_DONE "$W/build.log" || { echo "image build failed (see above)"; exit 1; }
mv "$W/out.img" "$ROOT/dist/$NAME.img"
EXTRACT_SIZE=$(stat -f %z "$ROOT/dist/$NAME.img" 2>/dev/null || stat -c %s "$ROOT/dist/$NAME.img")
EXTRACT_SHA=$(shasum -a 256 "$ROOT/dist/$NAME.img" | cut -d' ' -f1)
rm -f "$ROOT/dist/$NAME.img.xz"; xz -T0 -6 "$ROOT/dist/$NAME.img"
( cd "$ROOT/dist" && shasum -a 256 "$NAME.img.xz" > "$NAME.img.xz.sha256" )
DL_SIZE=$(stat -f %z "$ROOT/dist/$NAME.img.xz" 2>/dev/null || stat -c %s "$ROOT/dist/$NAME.img.xz")
DL_SHA=$(cut -d' ' -f1 "$ROOT/dist/$NAME.img.xz.sha256")
python3 - "$ROOT/dist/loop-imager.json" <<PYEOF
import json, sys
json.dump({"os_list": [{
    "name": "LOOP $VERSION (Raspberry Pi OS 64-bit)",
    "description": "Outreach videos on a loop, with Staff Display Tools. LOOP Setup opens at the first login.",
    "url": "http://localhost:8765/$NAME.img.xz",
    "icon": "http://localhost:8765/loop-icon.png",
    "release_date": "$(date +%Y-%m-%d)",
    "extract_size": $EXTRACT_SIZE, "extract_sha256": "$EXTRACT_SHA",
    "image_download_size": $DL_SIZE, "image_download_sha256": "$DL_SHA",
    "devices": ["pi4-64bit", "pi5-64bit"],
    "init_format": "cloudinit-rpi"}]}, open(sys.argv[1], "w"), indent=2)
PYEOF
cp "$ROOT/profiles/default/staff-icon.png" "$ROOT/dist/loop-icon.png"
rm -rf "$W"
echo "built dist/$NAME.img.xz ($(du -h "$ROOT/dist/$NAME.img.xz" | cut -f1))"
