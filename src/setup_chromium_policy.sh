#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Lock Chromium on a LOOP display Pi to the staff workflow, using Chromium's managed policies
# (system-wide, so staff can't change them in Settings). Run as: sudo bash setup_chromium_policy.sh
#   - Always private (Incognito): sign-ins, cookies and history are wiped when the window closes
#   - DuckDuckGo search, so staff aren't nudged to sign in to Google
#   - No browser sign-in or sync; password manager off
#   - Downloads go straight to the drop folder, bookmarks bar always shown
#   - No keyring (no password prompt when the browser first opens)
set -euo pipefail
DROP="$(python3 "$(dirname "$0")/loop_profile.py" get system.data_mount)/videos"
DIR=/etc/chromium/policies/managed
mkdir -p "$DIR"
cat > "$DIR/loop.json" <<EOF
{
  "IncognitoModeAvailability": 2,
  "DefaultSearchProviderEnabled": true,
  "DefaultSearchProviderName": "DuckDuckGo",
  "DefaultSearchProviderKeyword": "duckduckgo.com",
  "DefaultSearchProviderSearchURL": "https://duckduckgo.com/?q={searchTerms}",
  "DefaultSearchProviderSuggestURL": "https://duckduckgo.com/ac/?q={searchTerms}&type=list",
  "BrowserSignin": 0,
  "SyncDisabled": true,
  "PasswordManagerEnabled": false,
  "DownloadDirectory": "$DROP",
  "PromptForDownloadLocation": false,
  "BookmarkBarEnabled": true
}
EOF
chmod 644 "$DIR/loop.json"
python3 -m json.tool "$DIR/loop.json" >/dev/null && echo "policy file OK: $DIR/loop.json"

# Never use the desktop keyring: otherwise the first browser start asks staff to choose a keyring password.
# Nothing needs saving (private windows, no password manager). Removed with the package.
mkdir -p /etc/chromium.d
cat > /etc/chromium.d/90-loop-no-keyring <<'EOF'
# LOOP displays: never use the desktop keyring (avoids the keyring password prompt; nothing is saved)
export CHROMIUM_FLAGS="$CHROMIUM_FLAGS --password-store=basic"
EOF
chmod 644 /etc/chromium.d/90-loop-no-keyring
echo "policy file OK: /etc/chromium.d/90-loop-no-keyring"

echo "--- saved Wi-Fi connections (system-stored if psk-flags is 0)"
found=0
while IFS=: read -r name type file; do
  [ "$type" = "802-11-wireless" ] || continue
  found=1
  echo "$name | file: $file | psk-flags: $(nmcli -g 802-11-wireless-security.psk-flags con show "$name")"
done < <(nmcli -t -f NAME,TYPE,FILENAME con show)
[ "$found" = 1 ] || echo "none saved"
ls -l /etc/NetworkManager/system-connections/ 2>/dev/null
echo POLICY_DONE
