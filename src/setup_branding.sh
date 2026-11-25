#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
# Apply the profile's look to a display Pi's desktop. Run as the desktop user (no sudo needed).
#  - Wallpaper: the branded idle image (~/loop/idle.png; pre-rotated on a portrait display)
#  - Desktop: profile desktop color, white labels, only the Staff Tools icon (no Trash/drives),
#    icon placed where it doesn't cover the logo or message
#  - Window title bars: desktop color + white; menu highlight in the accent color (labwc themerc-override)
#  - Taskbar and selection colors: desktop/accent colors (user copies of the Pi themes, as Appearance
#    Settings makes them)
# Settings are written for the headless output and both HDMI ports, so they apply once a TV
# is connected. The first time, each file's original is kept (loop_undo.py) so removing LOOP puts it back.
set -euo pipefail
APP="${LOOP_APP:-$HOME/loop}"                         # package: /usr/lib/loop
PROFILE_PY="$APP/loop_profile.py"
WALLPAPER="${LOOP_WALLPAPER:-$(python3 "$PROFILE_PY" wallpaper 2>/dev/null)}"
[ -n "$WALLPAPER" ] && [ -f "$WALLPAPER" ] || WALLPAPER="$APP/idle.png"
NAVY="$(python3 "$PROFILE_PY" get colors.desktop)"
BLUE="$(python3 "$PROFILE_PY" get colors.accent)"
INK="#0f172b"; WHITE="#FFFFFF"; MUTED="#99a1af"
export XDG_RUNTIME_DIR="/run/user/$(id -u)" WAYLAND_DISPLAY=wayland-0
backup() { python3 "$APP/loop_undo.py" snapshot "$1" 2>/dev/null || true; }   # original kept, first time only
wrote() { python3 "$APP/loop_undo.py" wrote "$1" 2>/dev/null || true; }

[ -f "$WALLPAPER" ] || { echo "ABORT: wallpaper $WALLPAPER missing"; exit 1; }

# Staff Tools icon position: the landscape idle image has its logo top-left, so the icon goes
# top-right; on a turned display the icon goes top-left.
case "$(python3 "$PROFILE_PY" rotate)" in
  90|180|270) HDMI_ICON_X=24; HEADLESS_ICON_X=24 ;;  # turned idle art: its logo is no longer top-left
  *)
    HDMI_ICON_X=1780
    HEADLESS_ICON_X=1100
    HEADLESS_WIDTH="$(wlr-randr 2>/dev/null | awk '
      /^NOOP-1 / { headless=1; next }
      /^[^[:space:]]/ { headless=0 }
      headless && /\(current\)/ { split($1, mode, "x"); print mode[1] }
    ' || true)"
    if [[ "$HEADLESS_WIDTH" =~ ^[0-9]+$ ]] && (( HEADLESS_WIDTH > 140 )); then
      HEADLESS_ICON_X=$((HEADLESS_WIDTH - 140))
    fi
    ;;
esac

# --- desktop (pcmanfm), one file per output
PM="$HOME/.config/pcmanfm/default"
mkdir -p "$PM"
# The Pi's outputs, plus every output the running desktop reports (a VM's Virtual-1, other adapters, future models).
OUTPUTS="NOOP-1 HDMI-A-1 HDMI-A-2 $(wlr-randr 2>/dev/null | awk '/^[^[:space:]]/ {print $1}' | tr '\n' ' ' || true)"
for OUT in $(echo "$OUTPUTS" | tr ' ' '\n' | awk 'NF && !seen[$0]++'); do
  ICON_X="$HDMI_ICON_X"
  if [ "$OUT" = NOOP-1 ]; then ICON_X="$HEADLESS_ICON_X"; fi
  F="$PM/desktop-items-$OUT.conf"
  backup "$F"
  cat > "$F" <<EOF
[*]
desktop_bg=$NAVY
desktop_shadow=$INK
desktop_fg=$WHITE
desktop_font=Nunito Sans Bold 14
wallpaper=$WALLPAPER
wallpaper_mode=crop
show_home=0
show_trash=0
show_mounts=0
folder=$HOME/Desktop
tmargin=57
bmargin=5

[loop-staff-tools.desktop]
x=$ICON_X
y=80
EOF
  wrote "$F"
done

# --- window title bars and menus (labwc)
TR="$HOME/.config/labwc/themerc-override"
mkdir -p "${TR%/*}"
backup "$TR"
cat > "$TR" <<EOF
# LOOP display branding
window.active.title.bg.color: $NAVY
window.active.label.text.color: $WHITE
window.active.button.unpressed.image.color: $WHITE
window.inactive.title.bg.color: $INK
window.inactive.label.text.color: $MUTED
window.inactive.button.unpressed.image.color: $MUTED
menu.items.active.bg.color: $BLUE
menu.items.active.text.color: $WHITE
EOF
wrote "$TR"

# --- taskbar and selection colors
# Raspberry Pi OS's desktop start script (labwc-pi) deletes ~/.config/gtk-3.0/gtk.css at every login, so the
# colors go where its own Appearance Settings keeps them: a user copy of each Pi theme (light, dark and their
# large-screen variants) that imports the system theme and then sets the named colors the theme reads.
THEMES_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/themes"
for THEME in PiXtrix PiXonyx tPiXtrix tPiXonyx; do
  [ -f "/usr/share/themes/$THEME/gtk-3.0/gtk.css" ] || continue
  GC="$THEMES_DIR/$THEME/gtk-3.0/gtk.css"
  mkdir -p "$(dirname "$GC")"
  backup "$GC"
  cat > "$GC" <<EOF
@import url("/usr/share/themes/$THEME/gtk-3.0/gtk.css");
/* LOOP display branding */
@define-color bar_bg_color $NAVY;
@define-color bar_fg_color $WHITE;
@define-color theme_selected_bg_color $BLUE;
@define-color theme_selected_fg_color $WHITE;
EOF
  wrote "$GC"
done

# --- reload: window manager, desktop, taskbar
# (each step is skipped when no desktop is running, e.g. during a package install; it applies at next login)
if pgrep -x labwc >/dev/null; then kill -HUP "$(pgrep -x labwc)" && echo "window theme reloaded"; fi
pcmanfm --reconfigure >/dev/null 2>&1 && echo "desktop reloaded" || echo "desktop reload: will apply at next login"
if pkill -x wf-panel-pi; then echo "taskbar restarted"; fi
echo BRANDING_DONE
