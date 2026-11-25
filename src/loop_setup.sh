#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# loop-setup: set up this Pi as a LOOP display (installed as /usr/bin/loop-setup; run as root).
# The setup wizard and the Settings window are front ends to this command; it can also be run by hand:
#
#   sudo loop-setup --profile <name|dir> --site <site.json> [--user <name>]
#                   [--drive /dev/sda --erase-drive] [--backup-video <file.mp4>]
#                   [--idle-image <picture>] [--idle-portrait <picture>] [--logo-file <picture>]...
#   sudo loop-setup --profile-json <profile.json> --site <site.json> ...   (used by the setup wizard and Settings)
#   sudo loop-setup --apply        re-apply the settings already in /etc/loop (used after install/upgrade)
#
#   --profile       an organization profile: a name under /usr/share/loop/profiles, or a folder with
#                   profile.json and its artwork (logo-white.png, staff-icon.png, idle-screen*.png/mp4)
#   --profile-json  install this profile.json (usually {"basedOn": "<name>"} plus local changes); artwork kept
#   --logo-file     logo-white.png|svg or staff-icon.png: replaces that picture (an SVG logo becomes a PNG)
#   --reset-branding  remove the pictures added earlier, so the profile's own are used again
#   --site          this deployment's private settings (video library link, contact, displays, data drive)
#   --user          the desktop user who runs the display (default: the auto-login user)
#   --drive, --erase-drive   ERASE that USB drive and make it the data drive (videos, state, history)
#   --backup-video  copied to the SD card; plays if the USB drive or its videos are missing
#   --idle-image    your own idle screen (PNG or JPG, ideally 1920x1080); --idle-portrait: the same for a TV
#                   mounted on its side (1080x1920). Setup turns the right one into a short H.264 video for
#                   this display, rotated as its "rotate" setting says (0, 90, 180 or 270 degrees clockwise).
set -euo pipefail
LIB=/usr/lib/loop ETC=/etc/loop STATE=/var/lib/loop
[ "$(id -u)" -eq 0 ] || { echo "loop-setup must run as root (sudo)." >&2; exit 1; }
PROFILE="" PROFILE_JSON="" LOGOS=() RESET=0 SITE="" USER_NAME="" DRIVE="" ERASE=0 BACKUP="" APPLY=0 IDLE="" IDLE_P=""
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --site) SITE="$2"; shift 2 ;;
    --profile-json) PROFILE_JSON="$2"; shift 2 ;;
    --logo-file) LOGOS+=("$2"); shift 2 ;;
    --reset-branding) RESET=1; shift ;;
    --user) USER_NAME="$2"; shift 2 ;;
    --drive) DRIVE="$2"; shift 2 ;;
    --erase-drive) ERASE=1; shift ;;
    --backup-video) BACKUP="$2"; shift 2 ;;
    --idle-image) IDLE="$2"; shift 2 ;;
    --idle-portrait) IDLE_P="$2"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    -h|--help) sed -n '4,24p' "$0"; exit 0 ;;
    *) echo "loop-setup: unknown option $1 (see --help)" >&2; exit 2 ;;
  esac
done
say() { echo "loop-setup: $*"; }
mkdir -p "$ETC/branding" "$STATE"

# 1. Organization profile: profile.json plus its artwork into /etc/loop.
if [ -n "$PROFILE" ]; then
  if [ -d "/usr/share/loop/profiles/$PROFILE" ] && [ ! -d "$PROFILE" ]; then
    # A packaged profile: /etc/loop/profile.json only names it, so package upgrades bring its
    # improvements; local changes (setup wizard, Settings) go in this file on top of it.
    printf '{\n  "basedOn": "%s"\n}\n' "$PROFILE" > "$ETC/profile.json"
    rm -f "$ETC/branding/"*
    say "profile $PROFILE applied (packaged; artwork from /usr/share/loop/profiles/$PROFILE)"
  else
    # A profile folder of your own: copied in.
    [ -f "$PROFILE/profile.json" ] || { echo "loop-setup: no profile.json in $PROFILE" >&2; exit 1; }
    python3 -m json.tool "$PROFILE/profile.json" >/dev/null
    install -m 644 "$PROFILE/profile.json" "$ETC/profile.json"
    rm -f "$ETC/branding/"*
    find "$PROFILE" -maxdepth 1 -type f \( -name '*.png' -o -name '*.mp4' -o -name '*.svg' \) \
      -exec install -m 644 {} "$ETC/branding/" \;
    say "profile $(basename "$PROFILE") applied ($(ls "$ETC/branding" | wc -l | tr -d ' ') artwork files)"
  fi
fi

if [ -n "$PROFILE_JSON" ]; then
  python3 -m json.tool "$PROFILE_JSON" >/dev/null
  install -m 644 "$PROFILE_JSON" "$ETC/profile.json"
  say "profile settings applied"
fi
if [ "$RESET" = 1 ]; then rm -f "$ETC/branding/"*; say "earlier pictures removed (the profile's own are used)"; fi
for f in ${LOGOS[@]+"${LOGOS[@]}"}; do
  case "$(basename "$f")" in
    logo-white.svg)
      python3 - "$f" "$ETC/branding/logo-white.png" <<'PYEOF'
import sys, gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
GdkPixbuf.Pixbuf.new_from_file_at_scale(sys.argv[1], 1080, -1, True).savev(sys.argv[2], "png", [], [])
PYEOF
      chmod 644 "$ETC/branding/logo-white.png"; say "logo stored" ;;
    logo-white.png) install -m 644 "$f" "$ETC/branding/logo-white.png"; say "logo stored" ;;
    staff-icon.png) install -m 644 "$f" "$ETC/branding/staff-icon.png"; say "Staff Tools icon stored" ;;
    *) echo "loop-setup: --logo-file takes logo-white.png, logo-white.svg or staff-icon.png" >&2; exit 2 ;;
  esac
done

# 2. Site settings (private to this deployment).
if [ -n "$SITE" ]; then
  python3 -m json.tool "$SITE" >/dev/null
  install -m 644 "$SITE" "$ETC/site.json"
  say "site settings applied"
fi
[ -f "$ETC/profile.json" ] && [ -f "$ETC/site.json" ] || {
  echo "loop-setup: needs a profile and site settings: sudo loop-setup --profile <name> --site <site.json>" >&2; exit 1; }
P() { python3 "$LIB/loop_profile.py" "$@"; }

# 3. The desktop user who runs the display.
if [ -z "$USER_NAME" ]; then
  USER_NAME="$(P get system.user)"
  [ -n "$USER_NAME" ] || USER_NAME="$( (grep -rhs '^autologin-user=' /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.d/ || true) | tail -1 | cut -d= -f2)"
  [ -n "$USER_NAME" ] || USER_NAME="$( (getent passwd 1000 || true) | cut -d: -f1)"
fi
id "$USER_NAME" >/dev/null 2>&1 || { echo "loop-setup: user '$USER_NAME' not found (use --user)" >&2; exit 1; }
say "display user: $USER_NAME"

# 4. Data drive (only when asked: it erases the drive).
DATA="$(P get system.data_mount)"
# Older setups waited only 10 s for the data drive at boot; a USB drive can take longer to appear.
if grep -q " $DATA ext4 .*x-systemd.device-timeout=10s" /etc/fstab; then
  sed -i "s| $DATA ext4 \(.*\)x-systemd.device-timeout=10s| $DATA ext4 \1x-systemd.device-timeout=60s|" /etc/fstab
  say "data drive: boot now waits up to 60 s for it"
fi
if [ -n "$DRIVE" ]; then
  [ "$ERASE" = 1 ] || { echo "loop-setup: --drive erases $DRIVE; add --erase-drive to confirm" >&2; exit 1; }
  LOOP_USB_DEVICE="$DRIVE" LOOP_ASSUME_YES=1 SUDO_USER="$USER_NAME" bash "$LIB/setup_usb.sh" | tail -3
fi
if mountpoint -q "$DATA"; then
  install -d -o "$USER_NAME" -g "$USER_NAME" "$DATA/videos" "$DATA/state" "$DATA/logs"
  say "data drive at $DATA"
else
  say "WARNING: no data drive mounted at $DATA (videos, state and history need it; use --drive)"
fi

# 5. Chromium managed policy (private browsing, no sign-in or passwords, downloads to the drop folder).
bash "$LIB/setup_chromium_policy.sh" | grep -E 'policy file' | sed 's/^/loop-setup: /'

# 6. Backup video on the SD card.
if [ -n "$BACKUP" ]; then install -m 644 "$BACKUP" "$STATE/backup.mp4"; say "backup video stored"; fi

# The Staff Tools icon for the menu and taskbar, at a fixed place, from whichever profile is in use now.
ICON_SRC="$(P asset staff-icon.png)"
[ -n "$ICON_SRC" ] && install -m 644 "$ICON_SRC" "$STATE/staff-icon.png"

# 7. Idle screen: your own picture (optional), always played as a video (a still picture runs the Pi hotter).
idle_in() {  # picture, name: kept as the profile's idle art (PNG or JPG)
  local ext="${1##*.}"; ext="$(echo "$ext" | tr 'A-Z' 'a-z')"; [ "$ext" = jpeg ] && ext=jpg
  case "$ext" in png|jpg) ;; *) echo "loop-setup: $1 must be a PNG or JPG picture" >&2; exit 1 ;; esac
  rm -f "$ETC/branding/$2.png" "$ETC/branding/$2.jpg"
  install -m 644 "$1" "$ETC/branding/$2.$ext"
}
[ -z "$IDLE" ] || { idle_in "$IDLE" idle-screen; say "idle picture stored"; }
[ -z "$IDLE_P" ] || { idle_in "$IDLE_P" idle-screen-portrait; say "portrait idle picture stored"; }
bash "$LIB/setup_bootsplash.sh" | sed 's/^bootsplash: /loop-setup: boot screen: /'
python3 "$LIB/loop_idle_video.py" --auto $([ "$RESET" = 1 ] && echo --force) | sed 's/^loop-idle-video: /loop-setup: /'

# 8. The desktop user's part (VLC, services, browser bookmark, launchers, desktop look).
[ -e "/var/lib/systemd/linger/$USER_NAME" ] || touch "$STATE/linger-by-loop"  # removal turns it back off
loginctl enable-linger "$USER_NAME"
echo "$USER_NAME" > "$STATE/display-user"
UID_="$(id -u "$USER_NAME")"
runuser -u "$USER_NAME" -- env XDG_RUNTIME_DIR="/run/user/$UID_" HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)" \
  bash "$LIB/loop-user-setup" | sed 's/^loop-user-setup: /loop-setup:   /'
say "done. Staff Display Tools: double-click the video, then the Staff Tools icon on the taskbar."
