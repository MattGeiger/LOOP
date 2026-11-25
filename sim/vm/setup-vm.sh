#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Build loop-sim from scratch on a Mac with UTM and Docker: download and check the Debian 13 arm64
# cloud image, make the disks, seed, key and test password, create and boot the VM, then provision it.
# Everything generated goes in sim/vm/work/ (git-ignored).
set -euo pipefail
V="$(cd "$(dirname "$0")" && pwd)"; W="$V/work"; mkdir -p "$W"; cd "$W"
B=https://cloud.debian.org/images/cloud/trixie/latest
IMG=debian-13-generic-arm64.qcow2
[ -f "$IMG" ] || { curl -fsSLo SHA512SUMS "$B/SHA512SUMS"; curl -fsSLo "$IMG" "$B/$IMG"; }
grep " $IMG\$" SHA512SUMS | shasum -a 512 -c -
cp "$IMG" loop-sim.qcow2
docker run --rm -v "$W":/w debian:trixie-slim sh -c \
  'apt-get update -qq >/dev/null && apt-get install -y -qq qemu-utils >/dev/null &&
   qemu-img resize /w/loop-sim.qcow2 24G && qemu-img create -f qcow2 /w/data.qcow2 4G'
[ -f id_loop_sim ] || ssh-keygen -q -t ed25519 -N '' -C loop-sim -f id_loop_sim
[ -f test-password.txt ] || python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(16)))" > test-password.txt
chmod 600 id_loop_sim test-password.txt
"$V/make-seed.sh"
"$V/create-vm.sh"
# The seed must be on SCSI (USB appears too late for cloud-init); add a display.
osascript <<'OSA'
tell application "UTM"
  set vm to virtual machine named "loop-sim"
  set cfg to configuration of vm
  set drvs to drives of cfg
  set d3 to item 3 of drvs
  set interface of d3 to SCSI
  set item 3 of drvs to d3
  set drives of cfg to drvs
  set displays of cfg to {{hardware:"virtio-gpu-gl-pci", dynamic resolution:true}}
  update configuration of vm with cfg
  start vm
end tell
OSA
echo "Waiting for the VM address..."
for i in $(seq 1 60); do
  IP=$(osascript -e 'tell application "UTM" to query ip of virtual machine named "loop-sim"' 2>/dev/null | tr ',' '\n' | grep -oE '192\.168\.[0-9]+\.[0-9]+' | head -1 || true)
  [ -n "$IP" ] && break; sleep 5
done
echo "$IP" > ip.txt
SSH="ssh -i $W/id_loop_sim -o UserKnownHostsFile=$W/known_hosts -o StrictHostKeyChecking=accept-new -o BatchMode=yes loop@$IP"
until $SSH 'cloud-init status --wait' >/dev/null 2>&1; do sleep 5; done
scp -q -i "$W/id_loop_sim" -o UserKnownHostsFile="$W/known_hosts" -r "$V/standins" "loop@$IP:/tmp/"
$SSH 'sudo -S -p "" bash -s < /dev/stdin' < <(cat test-password.txt; cat "$V/provision.sh")
echo "loop-sim ready at $IP. Restart it to start the desktop."
