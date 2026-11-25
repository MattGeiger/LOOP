#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Install Setup Mode, Update Software and Go Live on a LOOP display Pi.
# Run as the desktop user in the Pi Connect remote shell; sudo asks for the password once.
#
# Desktop user files (no sudo):
#   ~/loop/  staff_tools.py staff_admin.py loop_state.py burnin_eval.py display_player.py
#   ~/burnin/       burnin_logger.py (retention follows the mode; starts a test after a restart)
# Root files (sudo):
#   /usr/libexec/loop/loop-maintenance-root                      the only privileged code
#   /usr/share/polkit-1/actions/com.templepdx.loop.maintenance.policy
#                                                             admin password dialog for it
#   /usr/local/bin/loop-maintenance                            command-line version
#
# Restarts the player and the recorder so they load the new code (the screen flashes once).
# Changes nothing else: read-only mode, SSH and the display mode stay as they are.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/loop"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

DATA="$(python3 "$SRC/loop_profile.py" get system.data_mount)"
mountpoint -q "$DATA" || { echo "ABORT: the USB data drive is not mounted at $DATA"; exit 1; }
[ "$(findmnt -n -o FSTYPE /)" != "overlay" ] || { echo "ABORT: read-only mode is on; files would be lost at restart"; exit 1; }
for f in loop_profile.py staff_tools.py staff_admin.py staff_help.py loop_state.py burnin_eval.py display_player.py burnin_logger.py \
         loop_maintenance_root.sh loop_maintenance.sh com.templepdx.loop.maintenance.policy; do
  [ -f "$SRC/$f" ] || { echo "ABORT: missing $f next to this script"; exit 1; }
done
python3 -m py_compile "$SRC"/loop_profile.py "$SRC"/staff_tools.py "$SRC"/staff_admin.py "$SRC"/staff_help.py "$SRC"/loop_state.py "$SRC"/burnin_eval.py \
  "$SRC"/display_player.py "$SRC"/burnin_logger.py
bash -n "$SRC/loop_maintenance_root.sh" && bash -n "$SRC/loop_maintenance.sh"

echo "== Desktop user files"
mkdir -p "$APP" "$HOME/burnin"
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
install -m 755 "$SRC/burnin_logger.py" "$HOME/burnin/"
rm -rf "$APP/__pycache__" "$SRC/__pycache__"

echo "== Root files (sudo)"
sudo install -d -m 755 /usr/libexec/loop
sudo install -o root -g root -m 755 "$SRC/loop_maintenance_root.sh" /usr/libexec/loop/loop-maintenance-root
sudo install -o root -g root -m 644 "$SRC/com.templepdx.loop.maintenance.policy" \
  /usr/share/polkit-1/actions/com.templepdx.loop.maintenance.policy
sudo install -o root -g root -m 755 "$SRC/loop_maintenance.sh" /usr/local/bin/loop-maintenance

echo "== Password check"
# A polkit rule that returns YES without checking the action (or that names ours) would make the
# admin password step a formality. Raspberry Pi OS's own rules each name specific actions.
rules=""
for r in $(sudo find /etc/polkit-1/rules.d /usr/share/polkit-1/rules.d -name '*.rules' 2>/dev/null); do
  body=$(sudo cat "$r")
  if grep -q 'com.templepdx.loop' <<<"$body" || { grep -q 'Result.YES' <<<"$body" && ! grep -q 'action.id' <<<"$body"; }; then
    rules+="$r"$'\n'
  fi
done
if [ -n "$rules" ]; then echo "Review these polkit rules (they may skip the password):"; printf '%s' "$rules"; else echo "No polkit rule skips the password for display administration."; fi

echo "== Restarting the recorder and the player"
systemctl --user restart burnin-logger.service
systemctl --user restart display-player.service
sleep 20
systemctl --user is-active display-player burnin-logger
/usr/local/bin/loop-maintenance status
echo MAINTENANCE_INSTALL_DONE
