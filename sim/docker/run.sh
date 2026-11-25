#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Start a virtual 1920x1080 display, then take the screenshots.
Xvfb :99 -screen 0 ${LOOP_SCREEN:-1920x1080}x24 -nolisten tcp >/dev/null 2>&1 &
export DISPLAY=:99
for i in 1 2 3 4 5 6 7 8 9 10; do [ -e /tmp/.X11-unix/X99 ] && break; sleep 0.3; done
exec dbus-run-session -- python3 sim/docker/ui_shots.py "$@"
