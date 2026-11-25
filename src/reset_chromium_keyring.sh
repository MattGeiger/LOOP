#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Scrub saved credentials from a LOOP display Pi and stop Chromium using the keyring.
# Run as: sudo bash reset_chromium_keyring.sh   (from the desktop user, with setup_chromium.py alongside)
#   1. /etc/chromium.d/90-loop-no-keyring: Chromium uses --password-store=basic, so it never
#      asks to unlock the keyring. Staff sign in through a private window, so nothing is saved.
#   2. Deletes the user's keyrings (~/.local/share/keyrings) - they may hold an admin's secrets.
#   3. Deletes the Chromium profile and cache (cookies, sign-ins, saved passwords, autofill,
#      history), then rebuilds it with only the LOOP settings (setup_chromium.py).
# Safe on these Pis: networking is wired (no Wi-Fi secret in the keyring) and Pi Connect keeps
# its login in ~/.config/com.raspberrypi.connect, not the keyring. Reboot afterwards.
set -euo pipefail
U="${SUDO_USER:?run with sudo from the desktop user}"
H="$(getent passwd "$U" | cut -d: -f6)"
SRC="$(cd "$(dirname "$0")" && pwd)"

pgrep -u "$U" -x chromium >/dev/null && { echo "ABORT: close Chromium first"; exit 1; }

cat > /etc/chromium.d/90-loop-no-keyring <<'EOF'
# LOOP displays: never use the desktop keyring (avoids the unlock prompt; nothing is saved)
export CHROMIUM_FLAGS="$CHROMIUM_FLAGS --password-store=basic"
EOF
chmod 644 /etc/chromium.d/90-loop-no-keyring
echo "flag file:"; cat /etc/chromium.d/90-loop-no-keyring

echo "deleting keyrings:"; ls -1 "$H/.local/share/keyrings/" || true
rm -f "$H/.local/share/keyrings/"*

echo "deleting Chromium profile and cache"
rm -rf "$H/.config/chromium" "$H/.cache/chromium"

sudo -u "$U" python3 "$SRC/setup_chromium.py"
echo RESET_DONE
