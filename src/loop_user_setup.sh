#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# loop-user-setup: the desktop user's part of LOOP setup. Run by loop-setup as the display user
# (installed as /usr/lib/loop/loop-user-setup). Safe to run again; changes only what LOOP owns:
#   - VLC: local-only control interface (127.0.0.1:8080, random password) and looping
#   - the loop-player and loop-history user services, started at login (older script installs retired)
#   - Chromium: downloads to the drop folder, one bookmark to the video library (skipped if Chromium is open)
#   - Staff Display Tools: taskbar launcher and the desktop icon (opens without an Execute prompt)
#   - the desktop look from the profile (setup_branding.sh)
# Before each change the original is recorded (loop_undo.py). `loop-user-setup --undo` puts back everything
# that still holds what LOOP set; the package runs it for the display user when LOOP is removed.
set -euo pipefail
LIB=/usr/lib/loop
PROFILE=(python3 "$LIB/loop_profile.py")
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
[ -S "$XDG_RUNTIME_DIR/bus" ] && export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
say() { echo "loop-user-setup: $*"; }
U() { python3 "$LIB/loop_undo.py" "$@"; }

if [ "${1:-}" = --undo ]; then
  systemctl --user stop loop-player.service loop-history.service 2>/dev/null || true
  rec="${XDG_STATE_HOME:-$HOME/.local/state}/loop/undo.json"
  if [ -f "$rec" ]; then U undo; else U undo --legacy; fi | sed 's/^loop-undo: /loop-user-setup: /'
  systemctl --user daemon-reload 2>/dev/null || true
  if pgrep -u "$(id -u)" -x labwc >/dev/null; then
    kill -HUP "$(pgrep -u "$(id -u)" -x labwc)" 2>/dev/null || true
    WAYLAND_DISPLAY=wayland-0 pcmanfm --reconfigure >/dev/null 2>&1 || true
    pkill -u "$(id -u)" -x wf-panel-pi || true
    say "desktop reloaded"
  fi
  echo LOOP_USER_UNDO_DONE
  exit 0
fi

# --- VLC: local control interface (Performance History and the player read it) and looping
VLCRC="$HOME/.config/vlc/vlcrc"
mkdir -p "$(dirname "$VLCRC")"; [ -f "$VLCRC" ] || : > "$VLCRC"
VLC_KEYS=(extraintf http-host http-port http-password loop)
U keys "$VLCRC" "${VLC_KEYS[@]}"
PW="$(grep -m1 '^http-password=.' "$VLCRC" | cut -d= -f2- || true)"
[ -n "$PW" ] || PW="$(python3 -c 'import secrets; print(secrets.token_hex(12))')"
setkey() { if grep -qE "^#?$1=" "$VLCRC"; then sed -i -E "0,/^#?$1=.*/s||$1=$2|" "$VLCRC"; else echo "$1=$2" >> "$VLCRC"; fi; }
setkey extraintf http; setkey http-host 127.0.0.1; setkey http-port 8080; setkey http-password "$PW"; setkey loop 1
chmod 600 "$VLCRC"
U wrote-keys "$VLCRC" "${VLC_KEYS[@]}"
say "VLC control interface on 127.0.0.1:8080"

# --- user services: start at login
UNITS="$HOME/.config/systemd/user"; WANTS="$UNITS/default.target.wants"
mkdir -p "$WANTS"
for old in display-player burnin-logger; do  # retire the services from the older script install
  if [ -e "$WANTS/$old.service" ]; then
    systemctl --user disable --now "$old.service" 2>/dev/null || rm -f "$WANTS/$old.service"
    say "retired $old.service"
  fi
done
for unit in loop-player loop-history; do
  ln -sf "/usr/lib/systemd/user/$unit.service" "$WANTS/$unit.service"
done
say "loop-player and loop-history start at login"

# --- Chromium: download folder and the library bookmark
if pgrep -x chromium >/dev/null; then
  say "Chromium is open: bookmark not changed (run loop-user-setup again after closing it)"
elif [ -n "$("${PROFILE[@]}" get content.library_url)" ]; then
  python3 "$LIB/setup_chromium.py" | grep -E 'downloads|bookmarks' | sed 's/^/loop-user-setup: chromium /'
else
  say "no video library link in site.json yet: bookmark skipped"
fi

# --- Staff Display Tools launchers
ICON="$("${PROFILE[@]}" asset staff-icon.png)"; ICON="${ICON:-$LIB/staff-icon.png}"
NAME="$("${PROFILE[@]}" get identity.launcher_name)"
mkdir -p "$HOME/Desktop"
LINK="$HOME/Desktop/loop-staff-tools.desktop"
cat > "$LINK.tmp" <<EOF
[Desktop Entry]
Type=Link
Name=$NAME
URL=loop-staff-tools://open
Icon=$ICON
EOF
LINK_CHANGED=0
if cmp -s "$LINK.tmp" "$LINK"; then rm -f "$LINK.tmp"; else
  [ -e "$LINK" ] && LINK_CHANGED=1
  mv -f "$LINK.tmp" "$LINK"
fi
gio mime x-scheme-handler/loop-staff-tools loop-staff-tools-link.desktop >/dev/null 2>&1 || \
  { mkdir -p "$HOME/.config"; touch "$HOME/.config/mimeapps.list"
    grep -q 'loop-staff-tools-link' "$HOME/.config/mimeapps.list" || printf '[Default Applications]\nx-scheme-handler/loop-staff-tools=loop-staff-tools-link.desktop\n' >> "$HOME/.config/mimeapps.list"; }
PANEL="$HOME/.config/wf-panel-pi/wf-panel-pi.ini"
mkdir -p "$(dirname "$PANEL")"; touch "$PANEL"
U panel "$PANEL"   # first time: keep the original launchers
python3 - "$PANEL" <<'EOF'
import sys
p = sys.argv[1]
lines = open(p).read().splitlines()
want = "launchers=loop-staff-tools x-www-browser pcmanfm"
out, in_panel, done = [], False, False
for ln in lines:
    if ln.startswith("["):
        if in_panel and not done:
            out.append(want); done = True
        in_panel = ln.strip() == "[panel]"
    if in_panel and ln.startswith("launchers="):
        if not done:
            out.append(want); done = True
        continue
    out.append(ln)
if not done:
    out = (["[panel]", want] + out) if "[panel]" not in lines else out + [want]
open(p, "w").write("\n".join(out) + "\n")
EOF
U panel "$PANEL"   # note LOOP's launchers
say "Staff Display Tools on the taskbar and the desktop ($NAME)"

# --- desktop look from the profile
LOOP_APP="$LIB" bash "$LIB/setup_branding.sh" | grep -E 'DONE|reload|restarted' | sed 's/^/loop-user-setup: branding /' || true

# --- a renamed desktop icon: the desktop program keeps the old label in memory, so restart it. On Raspberry Pi OS
# it runs under lwrespawn, which starts it again straight away; elsewhere the new label shows at the next login.
if [ "$LINK_CHANGED" = 1 ] && pgrep -u "$(id -u)" -f "lwrespawn .*pcmanfm" >/dev/null; then
  pkill -u "$(id -u)" -f "^pcmanfm --desktop" && say "desktop restarted (new icon name: $NAME)"
fi

# --- start (or restart) the services now if this user is logged in
if [ -S "$XDG_RUNTIME_DIR/bus" ]; then
  systemctl --user daemon-reload
  systemctl --user restart loop-history.service loop-player.service
  say "services restarted"
else
  say "services start at next login"
fi
echo LOOP_USER_SETUP_DONE
