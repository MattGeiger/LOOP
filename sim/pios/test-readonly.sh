#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Check read-only mode on loop-pios with Raspberry Pi OS's own raspi-config, as on a display Pi:
#   1. raspi-config nonint enable_overlayfs, restart -> root is an overlay; writes work but are temporary
#   2. restart again -> the test file is gone
#   3. raspi-config nonint disable_overlayfs, restart -> root is ext4 again
# Uses work/ip.txt, work/id_loop_pios and the throwaway work/test-password.txt.
set -euo pipefail
W="$(cd "$(dirname "$0")" && pwd)/work"; IP="$(cat "$W/ip.txt")"
ssh_() { ssh -i "$W/id_loop_pios" -o UserKnownHostsFile="$W/known_hosts" -o BatchMode=yes -o ConnectTimeout=3 "loop@$IP" "$@"; }
sudo_() { ssh_ "sudo -S -p '' $*" < "$W/test-password.txt"; }
wait_up() { sleep 8; for _ in $(seq 1 90); do ssh_ true 2>/dev/null && return 0; sleep 3; done; echo "VM did not come back"; exit 1; }
reboot_() { sudo_ systemctl reboot >/dev/null 2>&1 || true; wait_up; }
fstype() { ssh_ findmnt -no FSTYPE /; }
pass() { echo "PASS  $*"; }; fail() { echo "FAIL  $*"; exit 1; }

wait_up
[ "$(fstype)" = ext4 ] || fail "start: root is $(fstype), expected ext4 (read-only already on?)"
sudo_ raspi-config nonint enable_overlayfs >/dev/null
ssh_ grep -q overlayroot=tmpfs /boot/firmware/cmdline.txt && pass "raspi-config put overlayroot=tmpfs in cmdline.txt"
menu_has() { for _ in $(seq 1 40); do if ssh_ grep -q overlayroot=tmpfs /boot/efi/grub/grub.cfg; then [ "$1" = yes ] && return 0; else [ "$1" = no ] && return 0; fi; sleep 3; done; return 1; }
# loop-sim-grub.path rebuilds the VM kernel initramfs and the GRUB menu (about 30 s)
menu_has yes && pass "boot menu follows cmdline.txt" || fail "boot menu not updated"
reboot_
[ "$(fstype)" = overlay ] && pass "after restart: root is an overlay (read-only mode on)" || fail "root is $(fstype)"
ssh_ 'echo temp > ~/ro-test.txt' && pass "writes work while read-only (they go to memory)" || fail "home not writable"
reboot_
ssh_ '[ ! -e ~/ro-test.txt ]' && pass "after restart: the test file is gone" || fail "test file survived"
sudo_ raspi-config nonint disable_overlayfs >/dev/null
menu_has no && pass "read-only off: boot menu updated" || fail "boot menu still read-only"
reboot_
[ "$(fstype)" = ext4 ] && pass "after disable + restart: root is ext4 again" || fail "root is $(fstype)"
echo "READ-ONLY TEST PASSED"
