#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Build the loop-pios UTM VM from the official Raspberry Pi OS image in work/raspios.img (download and
# verification: see sim/README.md). Needs Docker and UTM. Generated files stay in work/ (git-ignored).
#   VM_NAME=loop-image SRC_IMG=loop-pios_<version>_arm64.img sim/pios/make-vm.sh   boots another image (in work/),
#   for example the LOOP Pi Imager image, under another name. The display card draws video and Chromium.
set -euo pipefail
P="$(cd "$(dirname "$0")" && pwd)"; W="$P/work"
[ -f "$W/${SRC_IMG:-raspios.img}" ] || { echo "work/${SRC_IMG:-raspios.img} missing"; exit 1; }
VM_NAME="${VM_NAME:-loop-pios}" SRC_IMG="${SRC_IMG:-raspios.img}"
if osascript -e 'tell application "UTM" to get name of every virtual machine' | tr ',' '\n' | sed 's/^ *//' | grep -qx "$VM_NAME"; then
  echo "A UTM VM named $VM_NAME already exists; delete it in UTM first (or rename it) to rebuild."; exit 1
fi
[ -f "$W/id_loop_pios" ] || ssh-keygen -q -t ed25519 -N '' -C loop-pios -f "$W/id_loop_pios"
[ -f "$W/test-password.txt" ] || python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(16)))" > "$W/test-password.txt"
chmod 600 "$W/id_loop_pios" "$W/test-password.txt"
HASH="$(docker run --rm -i debian:trixie-slim sh -c 'apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq openssl >/dev/null 2>&1; openssl passwd -6 -stdin' < "$W/test-password.txt")"
rm -rf "$W/seed" "$W/standins"; mkdir -p "$W/seed"; cp -R "$P/../vm/standins" "$W/standins"; cp "$P/loop-sim-grub.service" "$P/loop-sim-initramfs" "$P/loop-sim-grubcfg" "$W/"
sed -e "s|@PASSWORD_HASH@|$HASH|" -e "s|@SSH_KEY@|$(cat "$W/id_loop_pios.pub")|" "$P/user-data.template" > "$W/seed/user-data"
cp "$P/network-config" "$W/seed/network-config"
printf 'dsmode: local\ninstance_id: loop-pios-%s\n' "$(date +%s)" > "$W/seed/meta-data"
docker run --rm --privileged -e SRC_IMG="$SRC_IMG" -e DISK="$VM_NAME" -v "$W":/w -v "$P/build-image.sh":/build-image.sh:ro debian:trixie-slim bash /build-image.sh
osascript <<OSA
tell application "UTM"
  set vm to make new virtual machine with properties {backend:qemu, configuration:{name:"$VM_NAME", notes:"LOOP test bench: $SRC_IMG with a Debian arm64 kernel. See LOOP sim/README.md.", architecture:"aarch64", memory:2048, cpu cores:4, drives:{{interface:VirtIO, source:(POSIX file "$W/$VM_NAME.qcow2")}, {interface:USB, source:(POSIX file "$W/data-$VM_NAME.qcow2")}}, network interfaces:{{hardware:"virtio-net-pci", mode:shared}}, displays:{{hardware:"virtio-gpu-pci", dynamic resolution:true}}}}
  return id of vm
end tell
OSA
