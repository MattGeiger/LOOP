#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Runs inside a privileged arm64 Debian container (build-pi-image.sh): /w/base.img is the official Raspberry Pi
# OS image, /w/loop.deb the package. Writes /w/out.img: the same image with LOOP installed (nothing set up yet;
# LOOP Setup opens at the first login). Pi OS's own first boot (Pi Imager's user, Wi-Fi and SSH settings through
# cloud-init, growing the system partition to fill the card) is left exactly as it is.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq fdisk parted e2fsprogs zerofree >/dev/null
cp --sparse=always /w/base.img /w/out.img
truncate -s +1G /w/out.img                       # room for LOOP and its few extra packages
parted -s /w/out.img resizepart 2 100%
# No udev in a container, so each partition gets its own loop device at its offset.
read -r B_START B_SECT < <(sfdisk -d /w/out.img | awk -F'[=,]' '/out.img1/{print $2+0, $4+0}')
read -r R_START R_SECT < <(sfdisk -d /w/out.img | awk -F'[=,]' '/out.img2/{print $2+0, $4+0}')
LB=$(losetup -f --show -o $((B_START * 512)) --sizelimit $((B_SECT * 512)) /w/out.img)
LR=$(losetup -f --show -o $((R_START * 512)) --sizelimit $((R_SECT * 512)) /w/out.img)
e2fsck -pf "$LR" >/dev/null || true; resize2fs "$LR" >/dev/null
T=/t; mkdir -p $T; mount "$LR" $T; mount "$LB" $T/boot/firmware
for d in dev dev/pts proc sys; do mount --bind /$d $T/$d; done
cp /etc/resolv.conf $T/etc/resolv.conf.loop-build; mount --bind /etc/resolv.conf $T/etc/resolv.conf
printf '#!/bin/sh\nexit 101\n' > $T/usr/sbin/policy-rc.d; chmod 755 $T/usr/sbin/policy-rc.d   # start nothing
cp /w/loop.deb $T/tmp/loop.deb
chroot $T sh -c 'apt-get update -qq && apt-get install -y --no-install-recommends /tmp/loop.deb \
  -o Dpkg::Options::=--force-confold 2>&1 | grep -E "^(Setting up|Unpacking|E:)" | grep -iE "loop|inter|overlay|E:" || true
  apt-get install -y -qq overlayroot raspi-config >/dev/null 2>&1 || true; apt-get clean'
chroot $T dpkg -s loop-display | sed -n 's/^Version: /installed loop-display /p'
chroot $T bash /usr/lib/loop/setup_bootsplash.sh || true   # LOOP's boot screen from the first boot
rm -f $T/tmp/loop.deb $T/usr/sbin/policy-rc.d
umount $T/etc/resolv.conf; rm -f $T/etc/resolv.conf.loop-build
for d in sys proc dev/pts dev; do umount $T/$d; done
umount $T/boot/firmware; umount $T
zerofree "$LR"                                    # unused space compresses to nothing
losetup -d "$LR" "$LB"
echo IMAGE_DONE
