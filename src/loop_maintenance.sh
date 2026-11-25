#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# loop-maintenance: command-line version of Update Software and Setup Mode, for IT in the
# Pi Connect remote shell. Staff Display Tools does the same through its windows; both use the
# root helper (/usr/libexec/loop/loop-maintenance-root) and the shared state on the USB drive
# (loop_state.py), so either can pick up where the other left off.
#
#   loop-maintenance status        mode, read-only, update step, burn-in test, SSH (no changes)
#   loop-maintenance off           update step 1: read-only OFF at next boot, then restart
#   loop-maintenance check         list available updates by group
#   loop-maintenance update [GROUP...]   install updates (all by default; read-only must be off)
#   loop-maintenance repair        finish an interrupted install
#   loop-maintenance on            last step: read-only ON at next boot, then restart
#   loop-maintenance burnin        burn-in test report (pass/fail so far)
#   loop-maintenance setup-mode    return a live display to Setup Mode (keeps 7+ days of history)
#
# Installed as /usr/local/bin/loop-maintenance by install_maintenance.sh. sudo asks for the password.
set -euo pipefail
HELPER=/usr/libexec/loop/loop-maintenance-root
APP=/usr/lib/loop; [ -f "$APP/loop_state.py" ] || APP="$HOME/loop"  # package, else legacy scripts
PY() { local code="$1"; shift; python3 -c "import sys; sys.path.insert(0, '$APP'); import loop_state as s; $code" "$@"; }
confirm() { read -r -p "$1 Type yes to continue: " a; [ "$a" = "yes" ] || { echo "Cancelled."; exit 1; }; }
offer_reboot() {
  read -r -p "Restart now? The screen goes dark for about a minute. [y/N] " a
  if [ "$a" = "y" ] || [ "$a" = "Y" ]; then sudo "$HELPER" reboot; else echo "Restart later to continue."; fi
}

status() {
  PY "
print('Display:             ', __import__('socket').gethostname())
print('Mode:                ', s.mode().capitalize())
print('Read-only now / next:', 'ON' if s.ro_now() else 'OFF', '/', 'ON' if s.ro_next() else 'OFF')
d = s.maint()
print('Software update:     ', (d['stage'].replace('_', ' ') + (' (video resumed without read-only!)' if d.get('resume_without_ro') else '')) if d.get('stage') else 'none in progress')
t = s.burnin()['test']
print('Burn-in test:        ', t.get('state'), t.get('verdict', ''), t.get('started', ''), t.get('reason', ''))
print('SSH:                 ', 'on' if s.ssh_enabled() else 'off')
print('Root helper:         ', 'installed' if s.helper_installed() else 'NOT INSTALLED (run install_maintenance.sh)')
print('History kept:        ', int(s.retention_hours()), 'hours')
"
  echo "overlayroot package:  $(dpkg-query -W -f='${Version}' overlayroot 2>/dev/null || echo 'not installed (installed by the first update)')"
  SVC="$(PY "import loop_profile as p; print(p.player_service(), p.history_service())")"
  echo "Player / history:     $(systemctl --user is-active ${SVC% *}) / $(systemctl --user is-active ${SVC#* })"
}

case "${1:-status}" in
  status)
    status ;;
  off)
    if ! PY "sys.exit(0 if s.ro_now() or s.ro_next() else 1)"; then echo "Read-only mode is already off."; exit 0; fi
    confirm "Read-only mode turns OFF at the next restart. The video stays paused until updates are done and read-only is back on."
    sudo "$HELPER" ro-off
    PY "s.stop_test('Stopped for a software update'); s.set_maint('ro_off_pending', origin='ro')"
    offer_reboot ;;
  check)
    sudo "$HELPER" check ;;
  update)
    shift || true
    groups=("$@"); [ ${#groups[@]} -gt 0 ] || groups=(all)
    PY "sys.exit(1 if s.ro_now() else 0)" || { echo "Read-only mode is ON. Run: loop-maintenance off"; exit 1; }
    confirm "This installs updates: ${groups[*]}."
    PY "d = s.maint(); s.set_maint('installing', origin=d.get('origin', 'rw'), groups=sys.argv[1:])" "${groups[@]}"
    if sudo "$HELPER" update "${groups[@]}"; then
      PY "d = s.maint(); s.set_maint('installed', origin=d.get('origin', 'rw'))"
      echo "Updates installed. Restart to finish them."
      offer_reboot
    else
      PY "d = s.maint(); s.set_maint('ready', origin=d.get('origin', 'rw'), note='The last install did not finish.')"
      echo "The install did not finish. Try: loop-maintenance repair"; exit 1
    fi ;;
  repair)
    sudo "$HELPER" repair
    PY "d = s.maint(); d.get('stage') and s.set_maint('ready', origin=d.get('origin', 'rw'), note='Repair finished.')" ;;
  on)
    if PY "sys.exit(0 if s.ro_now() else 1)"; then echo "Read-only mode is already on."; exit 0; fi
    confirm "Read-only mode turns ON at the next restart, then the video resumes."
    sudo "$HELPER" ro-on
    PY "d = s.maint(); s.set_maint('ro_on_pending', origin=d.get('origin', 'ro'))"
    offer_reboot ;;
  burnin)
    python3 "$APP/burnin_eval.py" ;;
  setup-mode)
    confirm "This returns the display to Setup Mode (burn-in testing). Read-only mode and SSH are not changed."
    PY "s.set_mode('setup')"
    echo "Setup Mode is on. Open Staff Display Tools > Setup & burn-in." ;;
  *)
    sed -n '7,14p' "$0"; exit 2 ;;
esac
