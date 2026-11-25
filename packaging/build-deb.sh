#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Build the loop-display Debian package (architecture all) into dist/.
#   packaging/build-deb.sh [profile ...]     e.g.  packaging/build-deb.sh wth
# The default profile (LOOP's TemplePDX look) is always included; name other profiles under profiles/ to add them (an
# organization's own build). Uses Docker for dpkg-deb, so it runs on a Mac too.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; PK="$ROOT/packaging"
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$ROOT/src/staff_tools.py")"
[ -n "$VERSION" ] || { echo "no APP_VERSION in src/staff_tools.py"; exit 1; }
B="$ROOT/dist/build"; T="$B/loop-display"; rm -rf "$B"; mkdir -p "$T"
d() { mkdir -p "$T/$1"; }

# Code, Help and setup scripts.
d usr/lib/loop
cp "$ROOT"/src/*.py "$T/usr/lib/loop/"
cp -R "$ROOT/src/help" "$T/usr/lib/loop/help"
for s in setup_branding.sh setup_chromium_policy.sh setup_usb.sh setup_bootsplash.sh reset_chromium_keyring.sh; do
  install -m 755 "$ROOT/src/$s" "$T/usr/lib/loop/$s"
done
install -m 755 "$ROOT/src/loop_user_setup.sh" "$T/usr/lib/loop/loop-user-setup"
chmod 755 "$T"/usr/lib/loop/{display_player,staff_tools,burnin_logger,burnin_summary,burnin_eval,loop_profile,loop_idle_video,loop_undo,loop_settings,settings_ui}.py

# Commands, the privileged helper and its password policy.
d usr/bin; d usr/libexec/loop; d usr/share/polkit-1/actions
install -m 755 "$ROOT/src/loop_setup.sh" "$T/usr/bin/loop-setup"
install -m 755 "$ROOT/src/loop_maintenance.sh" "$T/usr/bin/loop-maintenance"
printf '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/loop/staff_tools.py "$@"\n' > "$T/usr/bin/loop-staff-tools"
chmod 755 "$T/usr/bin/loop-staff-tools"
printf '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/loop/loop_idle_video.py "$@"\n' > "$T/usr/bin/loop-idle-video"
printf '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/loop/settings_ui.py "$@"\n' > "$T/usr/bin/loop-setup-wizard"
chmod 755 "$T/usr/bin/loop-idle-video" "$T/usr/bin/loop-setup-wizard"
install -m 755 "$ROOT/src/loop_maintenance_root.sh" "$T/usr/libexec/loop/loop-maintenance-root"
install -m 644 "$ROOT/src/com.templepdx.loop.maintenance.policy" "$T/usr/share/polkit-1/actions/"

# User services, menu entries, LOOP's own assets, profiles, docs.
d usr/lib/systemd/user; d usr/share/applications; d usr/share/loop/assets; d usr/share/loop/profiles
install -m 644 "$PK"/systemd/*.service "$T/usr/lib/systemd/user/"
install -m 644 "$PK"/applications/*.desktop "$T/usr/share/applications/"
d etc/xdg/autostart
install -m 644 "$PK/autostart/loop-setup-wizard.desktop" "$T/etc/xdg/autostart/"  # until a display is set up
install -m 644 "$ROOT/assets/temple/temple-logo-white.png" "$T/usr/share/loop/assets/"
for p in default "$@"; do
  [ -f "$ROOT/profiles/$p/profile.json" ] || { echo "no profile $p"; exit 1; }
  d "usr/share/loop/profiles/$p"
  find "$ROOT/profiles/$p" -maxdepth 1 -type f \( -name 'profile.json' -o -name '*.png' -o -name '*.mp4' -o -name '*.svg' \) \
    -exec install -m 644 {} "$T/usr/share/loop/profiles/$p/" \;
done
d usr/share/doc/loop-display
install -m 644 "$ROOT/README.md" "$ROOT/TRADEMARKS.md" "$T/usr/share/doc/loop-display/"
printf 'LOOP (Local Outreach on Pi)\nCopyright (C) 2026 Matt Geiger, Temple Consulting, LLC.\nLicense: AGPL-3.0-or-later (/usr/share/common-licenses/AGPL-3 or https://www.gnu.org/licenses/agpl-3.0.html).\nOrganization profiles and their branding are excluded; see TRADEMARKS.md.\n' \
  > "$T/usr/share/doc/loop-display/copyright"
find "$T" -name __pycache__ -prune -exec rm -rf {} +

# Package metadata.
d DEBIAN
sed "s/@VERSION@/$VERSION/" "$PK/DEBIAN/control.in" > "$T/DEBIAN/control"
install -m 755 "$PK/DEBIAN/postinst" "$PK/DEBIAN/prerm" "$PK/DEBIAN/postrm" "$T/DEBIAN/"
SUFFIX="$( [ $# -gt 0 ] && echo "+$(IFS=+; echo "$*")" || true )"
OUT="loop-display_${VERSION}${SUFFIX}_all.deb"
docker run --rm -v "$ROOT/dist":/d debian:trixie-slim sh -c "
  cd /d/build/loop-display && find . -type f ! -path './DEBIAN/*' -exec md5sum {} + | sed 's# \./# #' > DEBIAN/md5sums &&
  dpkg-deb --root-owner-group -Zxz --build /d/build/loop-display /d/$OUT >/dev/null && dpkg-deb --info /d/$OUT | sed -n '1,4p;/Package/,/Depends/p'"
rm -rf "$B"
echo "built dist/$OUT ($(du -h "$ROOT/dist/$OUT" | cut -f1))"
