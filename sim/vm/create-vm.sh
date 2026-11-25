#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Create the loop-sim VM in UTM (QEMU backend, virtualized arm64, 4 cores, 2 GB like a Pi 4).
# Disks are imported (copied) into UTM: system disk, a 4 GB disk on USB as the data drive, and the seed ISO.
set -euo pipefail
W="$(cd "$(dirname "$0")" && pwd)/work"
osascript <<OSA
tell application "UTM"
  set sys to POSIX file "$W/loop-sim.qcow2"
  set dat to POSIX file "$W/data.qcow2"
  set seed to POSIX file "$W/seed.iso"
  set vm to make new virtual machine with properties {backend:qemu, configuration:{name:"loop-sim", notes:"LOOP test bench: Debian 13 arm64 + Raspberry Pi desktop packages. See LOOP sim/README.md.", architecture:"aarch64", memory:2048, cpu cores:4, drives:{{interface:VirtIO, source:sys}, {interface:USB, source:dat}, {removable:true, interface:USB, source:seed}}, network interfaces:{{hardware:"virtio-net-pci", mode:shared}}}}
  return id of vm
end tell
OSA
