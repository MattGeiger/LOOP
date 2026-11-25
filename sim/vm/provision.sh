#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Turn the loop-sim VM (Debian 13 arm64) into a Raspberry Pi OS-style LOOP test display.
# Run once over SSH after first boot:  ssh loop@<vm> 'sudo bash -s' < sim/vm/provision.sh
# Expects sim/vm/standins/ copied to /tmp/standins first (setup-vm.sh does both).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
USER_NAME="${LOOP_SIM_USER:-loop}"

# 1. Raspberry Pi archive with its current keyring (the old .key file is SHA-1 signed and rejected).
if [ ! -f /etc/apt/sources.list.d/raspi.list ]; then
  curl -fsSLo /tmp/rpi-keyring.deb \
    https://archive.raspberrypi.com/debian/pool/main/r/raspberrypi-archive-keyring/raspberrypi-archive-keyring_2025.1+rpt1_all.deb
  dpkg -i /tmp/rpi-keyring.deb
  echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.pgp] http://archive.raspberrypi.com/debian trixie main" \
    > /etc/apt/sources.list.d/raspi.list
  apt-get update -q
fi

# 2. The Pi desktop and the software LOOP uses (no Pi kernel or boot firmware).
apt-get install -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
  rpd-wayland-core rpd-preferences rpd-theme vlc chromium rpi-chromium-mods raspi-config \
  wlr-randr grim ffmpeg python3-gi gir1.2-gtk-3.0 overlayroot

# 3. Stand-ins for Pi-only pieces.
install -m 755 /tmp/standins/vcgencmd /usr/local/bin/vcgencmd
ln -sf /usr/local/bin/vcgencmd /usr/local/sbin/vcgencmd
if ! dpkg-divert --list /usr/bin/raspi-config | grep -q real; then
  dpkg-divert --local --rename --divert /usr/bin/raspi-config.real --add /usr/bin/raspi-config
fi
install -m 755 /tmp/standins/raspi-config /usr/bin/raspi-config
mkdir -p /etc/loop-sim /boot/firmware
[ -f /boot/firmware/cmdline.txt ] || cat /proc/cmdline > /boot/firmware/cmdline.txt

# 4. Desktop auto-login, as on the display Pis.
mkdir -p /etc/lightdm/lightdm.conf.d
SESSION="$(ls /usr/share/wayland-sessions/ 2>/dev/null | grep -m1 -E 'rpd-labwc|LXDE-pi-labwc|labwc' | sed 's/\.desktop$//')"
cat > /etc/lightdm/lightdm.conf.d/50-loop-sim.conf <<CONF
[Seat:*]
autologin-user=$USER_NAME
autologin-session=${SESSION:-rpd-labwc}
user-session=${SESSION:-rpd-labwc}
CONF
loginctl enable-linger "$USER_NAME"
systemctl set-default graphical.target
echo "PROVISION_DONE session=${SESSION:-rpd-labwc}"
