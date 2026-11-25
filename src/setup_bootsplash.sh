#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# The display's boot screen: the profile's logo on its desktop color instead of Raspberry Pi's (run as root by
# loop-setup; installed as /usr/lib/loop/setup_bootsplash.sh).
#   - a Plymouth theme "loop" (Raspberry Pi OS's own "pix" script, which centres one picture) with splash.png
#   - the firmware's rainbow test screen off (disable_splash=1 in config.txt) and the kernel's small logos off
#     (logo.nologo in cmdline.txt); both lines are marked so removal takes out only what LOOP added
# The initramfs (which holds the boot screen) is rebuilt only when the picture changes: it takes a minute on a Pi.
#   setup_bootsplash.sh            make or refresh LOOP's boot screen
#   setup_bootsplash.sh --remove   put Raspberry Pi OS's own boot screen back
set -euo pipefail
LIB=/usr/lib/loop THEMES=/usr/share/plymouth/themes T=/usr/share/plymouth/themes/loop
CONFIG=/boot/firmware/config.txt CMDLINE=/boot/firmware/cmdline.txt
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[ -d "$THEMES/pix" ] && command -v plymouth-set-default-theme >/dev/null || { echo "bootsplash: no Plymouth here, skipped"; exit 0; }

rebuild() { update-initramfs -u -k all >/dev/null 2>&1 && echo "bootsplash: boot files rebuilt" || echo "bootsplash: WARNING update-initramfs failed"; }

if [ "${1:-}" = --remove ]; then
  [ "$(plymouth-set-default-theme)" = loop ] && { plymouth-set-default-theme pix; CHANGED=1; }
  rm -rf "$T"
  [ -f "$CONFIG" ] && sed -i '/^# LOOP boot screen$/{N;N;d}' "$CONFIG"   # the marker, [all] and disable_splash
  [ -f "$CMDLINE" ] && sed -i 's/ logo\.nologo//' "$CMDLINE"
  [ "${CHANGED:-0}" = 1 ] && rebuild
  echo "bootsplash: Raspberry Pi OS boot screen restored"; exit 0
fi

LOGO="$(python3 "$LIB/loop_profile.py" asset logo-white.png)"
COLOR="$(python3 "$LIB/loop_profile.py" get colors.desktop)"
[ -n "$LOGO" ] && [ -n "$COLOR" ] || { echo "bootsplash: no logo or color in the profile, skipped"; exit 0; }
NEW="$(mktemp --suffix=.png)"; trap 'rm -f "$NEW"' EXIT
# 1920x1080 with the logo 720 px wide in the middle (the theme scales it to the screen).
ffmpeg -y -loglevel error -f lavfi -i "color=c=0x${COLOR#\#}:s=1920x1080" -i "$LOGO" \
  -filter_complex "[1]scale=720:-1[l];[0][l]overlay=(W-w)/2:(H-h)/2:format=auto" -frames:v 1 "$NEW"

CHANGED=0
mkdir -p "$T"
if ! cmp -s "$NEW" "$T/splash.png"; then
  install -m 644 "$NEW" "$T/splash.png"; CHANGED=1
fi
if [ ! -f "$T/loop.plymouth" ]; then
  cp "$THEMES/pix/pix.script" "$T/loop.script"
  printf '[Plymouth Theme]\nName=LOOP\nDescription=LOOP display boot screen\nModuleName=script\n\n[script]\nImageDir=%s\nScriptFile=%s/loop.script\n' \
    "$T" "$T" > "$T/loop.plymouth"
  CHANGED=1
fi
if [ "$(plymouth-set-default-theme)" != loop ]; then plymouth-set-default-theme loop; CHANGED=1; fi
if [ -f "$CONFIG" ] && ! grep -q '^# LOOP boot screen$' "$CONFIG"; then
  printf '\n# LOOP boot screen\n[all]\ndisable_splash=1\n' >> "$CONFIG"   # its own block: the end may be a model section
fi
if [ -f "$CMDLINE" ] && ! grep -q 'logo\.nologo' "$CMDLINE"; then
  sed -i '1 s/$/ logo.nologo/' "$CMDLINE"
fi
[ "$CHANGED" = 1 ] && rebuild
echo "bootsplash: LOOP boot screen $([ "$CHANGED" = 1 ] && echo set || echo unchanged)"
