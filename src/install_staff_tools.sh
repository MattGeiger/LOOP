#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Install Staff Display Tools (and the matching player update) on a display Pi.
# Run as the desktop user (no sudo needed).
#  - ~/loop/staff_tools.py (+ staff_admin.py, loop_state.py, burnin_eval.py), logo-white.png, staff-icon.png
#    (the root helper for Update Software and Setup Mode comes from install_maintenance.sh)
#  - Staff Display Tools in the app menu and taskbar, plus the Staff Tools desktop icon (named by identity.launcher_name)
#  - Ctrl+Alt+S opens it, even over the fullscreen video (user labwc rc.xml, merged with system)
#  - updated display_player.py (staff idle switch, returns to fullscreen), then restarts it
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/loop"
APPLICATIONS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_LINK="$HOME/Desktop/loop-staff-tools.desktop"
LINK_SCHEME=loop-staff-tools
LINK_HANDLER=loop-staff-tools-display-link.desktop
LINK_MIME="x-scheme-handler/$LINK_SCHEME"
APP_NAME="Staff Display Tools"
LAUNCHER_NAME="$(python3 "$SRC/loop_profile.py" get identity.launcher_name)"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

if ! command -v gio >/dev/null; then
  printf '%s\n' 'GIO is required to register the Staff Tools desktop link.' >&2
  exit 1
fi
mkdir -p "$APP" "$APPLICATIONS" "$HOME/Desktop"

install -m 755 "$SRC/staff_tools.py" "$SRC/display_player.py" "$SRC/burnin_eval.py" "$APP/"
install -m 644 "$SRC/staff_admin.py" "$SRC/loop_state.py" "$APP/"
[ -f "$SRC/temple-logo-white.png" ] && install -m 644 "$SRC/temple-logo-white.png" "$APP/"
install -m 644 "$SRC/staff_help.py" "$APP/"
install -m 644 "$SRC/loop_profile.py" "$APP/"
for f in profile.json site.json; do  # organization profile and this deployment's private settings
  if [ -f "$SRC/$f" ]; then install -m 644 "$SRC/$f" "$APP/$f"; fi
done
rm -rf "$APP/help" && mkdir -p "$APP/help/images"
cp "$SRC"/help/*.md "$APP/help/"
cp "$SRC"/help/images/*.png "$APP/help/images/" 2>/dev/null || true  # screenshots are optional
install -m 644 "$SRC/logo-white.png" "$SRC/staff-icon.png" "$APP/"

# Replace a launcher atomically and leave an identical installed copy in place.
write_launcher() (
  destination="$1"
  temporary="$(mktemp "${destination%/*}/.loop-launcher.XXXXXX")"
  trap 'rm -f -- "$temporary"' EXIT
  cat > "$temporary"
  chmod 644 "$temporary"
  if ! cmp -s "$temporary" "$destination"; then
    mv -f -- "$temporary" "$destination"
  fi
)

write_launcher "$APPLICATIONS/loop-staff-tools.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Change the video, show the idle screen, check the display
Exec=python3 $APP/staff_tools.py
Icon=$APP/staff-icon.png
Terminal=false
Categories=Utility;
EOF

# PCManFM prompts for a desktop application entry. Register a user-level link
# handler first so that the desktop icon can launch without changing that policy.
write_launcher "$APPLICATIONS/$LINK_HANDLER" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Exec=/usr/bin/python3 "$APP/staff_tools.py" %u
Icon=$APP/staff-icon.png
Terminal=false
NoDisplay=true
MimeType=$LINK_MIME;
EOF
gio mime "$LINK_MIME" "$LINK_HANDLER"

write_launcher "$DESKTOP_LINK" <<EOF
[Desktop Entry]
Type=Link
Name=$LAUNCHER_NAME
URL=$LINK_SCHEME://open
Icon=$APP/staff-icon.png
EOF

# Keyboard shortcut Ctrl+Alt+S (labwc runs with -m, so this merges with the system config)
RC="$HOME/.config/labwc/rc.xml"
if [ ! -f "$RC" ]; then  # fresh system: no user labwc config yet
  mkdir -p "$(dirname "$RC")"
  printf '<?xml version="1.0"?>\n<openbox_config xmlns="http://openbox.org/3.4/rc">\n</openbox_config>\n' > "$RC"
fi
if ! grep -q "staff_tools.py" "$RC"; then
  cp -p "$RC" "$RC.bak-loop-$(date +%Y%m%d-%H%M%S)"
  python3 - "$RC" "$APP/staff_tools.py" <<'EOF'
import sys
rc, tool = sys.argv[1], sys.argv[2]
s = open(rc).read()
block = (f'<keyboard>\n<keybind key="C-A-s">\n<action name="Execute" command="python3 {tool}" />\n'
         '</keybind>\n</keyboard>\n')
s = s.replace("</openbox_config>", block + "</openbox_config>")
open(rc, "w").write(s)
EOF
fi
kill -HUP "$(pgrep -x labwc)" && echo "labwc reloaded"
grep -A2 'C-A-s' "$RC"

# Taskbar: Staff Display Tools first (reachable with the mouse after double-clicking the video);
# terminal launcher removed for staff simplicity.
PANEL="$HOME/.config/wf-panel-pi/wf-panel-pi.ini"
mkdir -p "$(dirname "$PANEL")"; touch "$PANEL"
cp -p "$PANEL" "$PANEL.bak-loop-$(date +%Y%m%d-%H%M%S)"
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
    if "[panel]" not in lines:
        out = ["[panel]"] + out
        out.insert(1, want)
    else:
        out.append(want)
open(p, "w").write("\n".join(out) + "\n")
EOF
grep -A1 '^\[panel\]' "$PANEL"; grep '^launchers=' "$PANEL"
pkill -x wf-panel-pi && echo "taskbar restarted (lwrespawn brings it back)"

systemctl --user restart display-player.service
sleep 15
systemctl --user is-active display-player
tail -n 2 "$(python3 "$APP/loop_profile.py" get system.data_mount)/logs/player.log"
echo STAFF_TOOLS_DONE
