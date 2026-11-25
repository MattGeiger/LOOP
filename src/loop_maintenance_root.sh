#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# loop-maintenance-root: the only privileged part of LOOP display maintenance.
# Installed root-owned as /usr/libexec/loop/loop-maintenance-root (install_maintenance.sh).
# Called by Staff Display Tools through pkexec (Raspberry Pi OS password dialog) and by the
# loop-maintenance command through sudo. It accepts exactly one of these actions:
#
#   selftest         prove the password dialog works; changes nothing
#   ro-off           read-only mode OFF at next boot (raspi-config disable_overlayfs)
#   ro-on            read-only mode ON at next boot (raspi-config enable_overlayfs)
#   check            refresh package lists; print one line per group: GROUP<TAB>COUNT<TAB>names
#   update GROUP...  install updates for the groups named (all | system | vlc | connect | chromium)
#   repair           finish an interrupted install (dpkg --configure -a; apt-get -f install)
#   ssh-off          stop and disable SSH (Go Live; raspi-config do_ssh 1)
#   ssh-on           enable and start SSH (raspi-config do_ssh 0)
#   reboot           restart now
#   settings DIR [DRIVE]  apply settings from the setup wizard or Settings: DIR (the caller's own folder under
#                    /run/user/<uid>) holds profile.json, site.json and optional pictures; DRIVE (a whole USB
#                    disk, setup wizard only) is ERASED and becomes the data drive. Files are copied into a
#                    root-only folder and checked (loop_settings.py check) before loop-setup installs them.
#
# raspi-config functions verified on Raspberry Pi OS trixie (Nov 2026). enable_overlayfs
# installs overlayroot itself if missing, which needs internet, so every update installs it.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive
CMDLINE=/boot/firmware/cmdline.txt
APT_OPTS=(-y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

[ "$(id -u)" -eq 0 ] || { echo "Must run as root (via pkexec or sudo)." >&2; exit 1; }

# Package-name patterns for the named groups. "system" is everything else.
group_of() {
  case "$1" in
    vlc|vlc-*|libvlc*|libvlccore*) echo vlc ;;
    rpi-connect*) echo connect ;;
    chromium|chromium-*|rpi-chromium-*) echo chromium ;;
    *) echo system ;;
  esac
}

upgradable() {  # names of upgradable packages, one per line
  apt list --upgradable 2>/dev/null | awk -F/ 'NR>1 && $1 != "" {print $1}'
}

require_rw() {
  if [ "$(findmnt -n -o FSTYPE /)" = "overlay" ]; then
    echo "ERROR: read-only mode is active, so changes would be lost at restart." >&2; exit 1
  fi
}

require_net() {
  if ! getent hosts archive.raspberrypi.com >/dev/null 2>&1; then
    echo "ERROR: no internet connection (cannot reach archive.raspberrypi.com)." >&2; exit 3
  fi
}

dpkg_broken() {  # true if a previous install was interrupted
  [ -n "$(dpkg --audit 2>/dev/null)" ]
}

case "${1:-}" in
  selftest)
    echo "Admin access confirmed on $(hostname)." ;;
  ro-off)
    # raspi-config removes exactly "overlayroot=tmpfs ", so take LOOP's :recurse=0 off first (see ro-on).
    sed -i 's/overlayroot=tmpfs:recurse=0 /overlayroot=tmpfs /' "$CMDLINE"
    raspi-config nonint disable_overlayfs
    if grep -q 'overlayroot=tmpfs' "$CMDLINE"; then echo "ERROR: read-only is still set for the next boot." >&2; exit 1; fi
    echo "Read-only mode will be OFF after the next restart." ;;
  ro-on)
    dpkg -s overlayroot >/dev/null 2>&1 || require_net  # raspi-config installs it if missing
    raspi-config nonint enable_overlayfs
    if ! grep -q 'overlayroot=tmpfs' "$CMDLINE"; then echo "ERROR: read-only was not set for the next boot." >&2; exit 1; fi
    # Only the SD card is read-only: by default overlayroot also puts every other drive in /etc/fstab under a RAM
    # layer (recurse=1), so videos, downloads, the burn-in test and Performance History written to the USB data
    # drive would be lost at the next restart. recurse=0 writes them straight to the drive.
    sed -i 's/overlayroot=tmpfs /overlayroot=tmpfs:recurse=0 /' "$CMDLINE"
    grep -q 'overlayroot=tmpfs:recurse=0' "$CMDLINE" || { echo "ERROR: could not keep the USB data drive writable." >&2; exit 1; }
    echo "Read-only mode will be ON after the next restart." ;;
  check)
    require_net
    if dpkg_broken; then echo "REPAIR	1	an earlier install was interrupted"; fi
    apt-get update -qq >/dev/null
    declare -A count names
    for g in system vlc connect chromium; do count[$g]=0; names[$g]=""; done
    while read -r p; do
      [ -n "$p" ] || continue
      g=$(group_of "$p"); count[$g]=$((count[$g] + 1)); names[$g]+="$p "
    done < <(upgradable)
    dpkg -s overlayroot >/dev/null 2>&1 || { count[system]=$((count[system] + 1)); names[system]+="overlayroot(new) "; }
    for g in system vlc connect chromium; do printf '%s\t%s\t%s\n' "$g" "${count[$g]}" "${names[$g]% }"; done ;;
  update)
    shift
    [ $# -gt 0 ] || { echo "Usage: loop-maintenance-root update all|system|vlc|connect|chromium..." >&2; exit 2; }
    require_rw; require_net
    if dpkg_broken; then echo "== Finishing an interrupted install first"; dpkg --configure -a; apt-get "${APT_OPTS[@]}" -f install; fi
    echo "== Refreshing the package lists"
    apt-get update
    if [[ " $* " == *" all "* ]]; then
      echo "== Installing all updates"
      apt-get "${APT_OPTS[@]}" full-upgrade
    else
      want=" $* "; pkgs=()
      while read -r p; do
        [ -n "$p" ] || continue
        [[ "$want" == *" $(group_of "$p") "* ]] && pkgs+=("$p")
      done < <(upgradable)
      if [ ${#pkgs[@]} -eq 0 ]; then
        echo "== Nothing to update in: $*"
      else
        echo "== Installing ${#pkgs[@]} update(s): ${pkgs[*]}"
        apt-get "${APT_OPTS[@]}" install --only-upgrade "${pkgs[@]}"
      fi
    fi
    if ! dpkg -s overlayroot >/dev/null 2>&1; then
      echo "== Installing overlayroot (needed for read-only mode)"
      apt-get "${APT_OPTS[@]}" install overlayroot
    fi
    if [ -f /run/reboot-required ]; then echo "== A restart is needed to finish these updates."; fi
    echo "== Updates finished." ;;
  repair)
    require_rw
    echo "== Finishing any interrupted install"
    dpkg --configure -a
    apt-get "${APT_OPTS[@]}" -f install
    if dpkg_broken; then echo "ERROR: packages are still not fully installed:" >&2; dpkg --audit >&2; exit 1; fi
    echo "== Package system is healthy." ;;
  ssh-off)
    raspi-config nonint do_ssh 1
    if systemctl is-enabled ssh >/dev/null 2>&1; then echo "ERROR: SSH is still enabled." >&2; exit 1; fi
    echo "SSH is off." ;;
  ssh-on)
    raspi-config nonint do_ssh 0
    echo "SSH is on." ;;
  reboot)
    sync
    systemctl reboot ;;
  settings)
    require_rw
    src="${2:-}"; drive="${3:-}"
    caller="${PKEXEC_UID:-${SUDO_UID:-0}}"
    case "$src" in "/run/user/$caller/loop-settings-"*) ;; *) echo "ERROR: settings must come from your own runtime folder." >&2; exit 2 ;; esac
    [ -d "$src" ] && [ ! -L "$src" ] && [ "$(stat -c %u "$src")" = "$caller" ] || { echo "ERROR: $src is not your settings folder." >&2; exit 2; }
    work="$(mktemp -d /run/loop-settings.XXXXXX)"; trap 'rm -rf "$work"' EXIT
    for f in "$src"/*; do
      [ -f "$f" ] && [ ! -L "$f" ] || continue
      case "$(basename "$f")" in *[!A-Za-z0-9._-]*) continue ;; esac
      cp --no-dereference -- "$f" "$work/"
    done
    python3 /usr/lib/loop/loop_settings.py check "$work" || { echo "ERROR: the settings were not accepted; nothing was changed." >&2; exit 1; }
    args=(--profile-json "$work/profile.json" --site "$work/site.json")
    [ -f "$work/reset-branding" ] && args+=(--reset-branding)
    for f in "$work"/logo-white.* "$work"/staff-icon.png; do [ -f "$f" ] && args+=(--logo-file "$f"); done
    [ -f "$work/idle-screen.png" ] && args+=(--idle-image "$work/idle-screen.png")
    [ -f "$work/idle-screen.jpg" ] && args+=(--idle-image "$work/idle-screen.jpg")
    [ -f "$work/idle-screen-portrait.png" ] && args+=(--idle-portrait "$work/idle-screen-portrait.png")
    [ -f "$work/idle-screen-portrait.jpg" ] && args+=(--idle-portrait "$work/idle-screen-portrait.jpg")
    if [ -n "$drive" ]; then
      [ "$(lsblk -dno TRAN,TYPE "$drive" 2>/dev/null | tr -s ' ')" = "usb disk" ] || { echo "ERROR: $drive is not a USB drive." >&2; exit 2; }
      args+=(--drive "$drive" --erase-drive)
    fi
    loop-setup "${args[@]}"
    echo "== Settings saved." ;;
  *)
    echo "Usage: loop-maintenance-root selftest|ro-off|ro-on|check|update GROUP...|repair|ssh-off|ssh-on|reboot|settings DIR [DRIVE]" >&2; exit 2 ;;
esac
