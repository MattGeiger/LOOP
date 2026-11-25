#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Assemble one display's LOOP install folder (what the package will eventually contain):
#   LOOP code (src/), the profile's artwork and profile.json, the Temple Consulting About logo,
#   and that deployment's site.json.
#   stage-loop.sh <profile> <site.json> <output dir>     e.g.  stage-loop.sh wth ../vm/site.sim.json work/stage
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROFILE="${1:?profile name under profiles/}"; SITE="${2:?site.json path}"; OUT="${3:?output dir}"
rm -rf "$OUT"; mkdir -p "$OUT"
cp -R "$ROOT/src/." "$OUT/"
find "$ROOT/profiles/$PROFILE" -maxdepth 1 -type f \( -name '*.png' -o -name '*.mp4' -o -name 'profile.json' \) \
  -exec cp {} "$OUT/" \;
cp "$ROOT/assets/temple/temple-logo-white.png" "$OUT/"
cp "$SITE" "$OUT/site.json"
find "$OUT" -name __pycache__ -prune -exec rm -rf {} +
echo "staged $(find "$OUT" -type f | wc -l | tr -d ' ') files in $OUT"
