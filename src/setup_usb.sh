#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# One-time USB data drive setup for a LOOP display Pi. Run as: sudo bash setup_usb.sh
# ERASES /dev/sda1, formats it ext4 (label from system.data_label, LOOPDATA by default), mounts it at
# system.data_mount (/mnt/loopdata by default) at every boot
# (nofail, so the Pi still boots without it), and creates videos/ state/ logs/ for the desktop user.
set -euo pipefail
PROFILE_PY="$(dirname "$0")/loop_profile.py"
DEV="${LOOP_USB_DEVICE:-/dev/sda}"
case "$DEV" in *[0-9]) PART="${DEV}p1" ;; *) PART="${DEV}1" ;; esac
MNT="$(python3 "$PROFILE_PY" get system.data_mount)"
LABEL="$(python3 "$PROFILE_PY" get system.data_label)"
MODEL="$(python3 "$PROFILE_PY" get system.usb_model)"
OWNER="${SUDO_USER:?run with sudo from the desktop user}"

# Safety: only ever touch a USB drive, never the SD card; optionally only the expected model.
[ "$(lsblk -dno TRAN "$DEV")" = "usb" ] || { echo "ABORT: $DEV is not a USB disk"; exit 1; }
if [ -n "$MODEL" ]; then
  lsblk -dno MODEL "$DEV" | grep -qF "$MODEL" || { echo "ABORT: drive model is not '$MODEL'"; exit 1; }
fi
lsblk -dno SIZE,MODEL "$DEV"
if [ "${LOOP_ASSUME_YES:-}" != 1 ]; then  # set LOOP_ASSUME_YES=1 for unattended installs
  read -r -p "This ERASES $DEV. Type yes to continue: " a; [ "$a" = "yes" ] || { echo "Cancelled."; exit 1; }
fi
# A blank drive has no partition yet: create one spanning the drive.
if [ ! -b "$PART" ]; then
  for m in $(lsblk -nro MOUNTPOINTS "$DEV"); do umount "$m"; done
  echo 'type=83' | sfdisk -q "$DEV"
  partprobe "$DEV" 2>/dev/null || true; udevadm settle 2>/dev/null || true
  for _ in $(seq 1 20); do [ -b "$PART" ] && break; sleep 0.5; done
fi
[ -b "$PART" ] || { echo "ABORT: $PART missing"; exit 1; }

# Unmount the desktop's automount, then format.
for m in $(lsblk -nro MOUNTPOINTS "$PART"); do umount "$m"; done
mkfs.ext4 -F -q -L "$LABEL" -m 0 "$PART"
UUID="$(blkid -s UUID -o value "$PART")"

# Mount at boot by UUID; x-gvfs-hide keeps it out of the desktop's drive list.
cp -p /etc/fstab "/etc/fstab.bak-loopdata-$(date +%Y%m%d-%H%M%S)"
grep -v " $MNT " /etc/fstab > /etc/fstab.new || true
echo "UUID=$UUID $MNT ext4 defaults,noatime,nofail,x-systemd.device-timeout=60s,x-gvfs-hide 0 2" >> /etc/fstab.new
mv /etc/fstab.new /etc/fstab
mkdir -p "$MNT"
systemctl daemon-reload
for m in $(lsblk -nro MOUNTPOINTS "$PART"); do umount "$m"; done   # in case the desktop re-mounted it
mount "$MNT"

mkdir -p "$MNT/videos" "$MNT/state" "$MNT/logs"
chown "$OWNER:$OWNER" "$MNT" "$MNT/videos" "$MNT/state" "$MNT/logs"

echo "--- result"
grep " $MNT " /etc/fstab
findmnt -n "$MNT"
ls -la "$MNT"
df -h "$MNT" | tail -1
echo USB_SETUP_DONE
