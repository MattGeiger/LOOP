#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Build the cloud-init seed ISO for loop-sim from user-data.template.
# Uses work/test-password.txt (a throwaway test password) and work/id_loop_sim.pub. macOS only (hdiutil).
set -euo pipefail
V="$(cd "$(dirname "$0")" && pwd)"; W="$V/work"
HASH="$(docker run --rm -i debian:trixie-slim sh -c 'apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq openssl >/dev/null 2>&1; openssl passwd -6 -stdin' < "$W/test-password.txt")"
KEY="$(cat "$W/id_loop_sim.pub")"
rm -rf "$W/seed" && mkdir -p "$W/seed"
sed -e "s|@PASSWORD_HASH@|$HASH|" -e "s|@SSH_KEY@|$KEY|" "$V/user-data.template" > "$W/seed/user-data"
printf 'instance-id: loop-sim-%s\nlocal-hostname: loop-sim\n' "$(date +%s)" > "$W/seed/meta-data"
rm -f "$W/seed.iso"
hdiutil makehybrid -quiet -iso -joliet -default-volume-name cidata -o "$W/seed.iso" "$W/seed"
echo "seed: $W/seed.iso"
