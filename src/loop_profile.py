#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""LOOP configuration: the organization's profile and this deployment's site settings.

Nothing organization-specific is written into LOOP's code. It comes from two JSON files:

  profile.json  the organization's identity: names, wording, staff contact, branding notice.
                Safe to share; a profile for another organization is just another file.
  site.json     this deployment's private settings: the video library link and its name,
                and each display's hostname and orientation. Never committed to LOOP.

Both are looked for in $LOOP_CONFIG_DIR, then beside this script (an installer's staging folder or
the app folder), then /etc/loop, then ~/loop. Values
are merged over the neutral defaults below, so a missing file or key never breaks a display.

Text in Help guides and windows can use {{dotted.key}} placeholders, filled by fill().
Command line (for the shell installers):  loop_profile.py get system.data_mount
"""
import copy
import json
import os
import re
import socket
import sys

APP_DIR = os.path.expanduser("~/loop")          # legacy script install (before the package)
CODE_DIR = os.path.dirname(os.path.abspath(__file__))  # /usr/lib/loop when installed as a package
STATE_DIR = "/var/lib/loop"                             # SD-card files: backup video
ROOT_HELPER = "/usr/libexec/loop/loop-maintenance-root"

DEFAULTS = {
    "schemaVersion": 1,
    "identity": {
        "organization": "",              # the organization the displays belong to
        "website": "",
        "displays_name": "the displays",  # how staff refer to the screens
        "contact": "the person who looks after the displays",  # who staff call
        "launcher_name": "Staff Tools",   # desktop icon label
        "branding_notice": "",            # shown in About when the profile's branding is not open source
    },
    "content": {
        "library_name": "the video library",  # what staff call the video library
        "library_url": "",                    # site.json: where staff download approved videos
        "bookmark_name": "Video library",
        "keep_videos": 3,
    },
    "displays": {},  # site.json: {"<hostname>": {"orientation": "landscape" | "portrait-cw", "rotate": 0|90|180|270,
                     #                            "label": "..."}}
    "colors": {
        "desktop": "#0c111d",   # desktop background, title bars and taskbar
        "accent": "#475cb8",    # menu and selection highlight
    },
    # Staff Display Tools colors (named tokens used in its styles). The default is LOOP's own theme:
    # TemplePDX.com "Twilight Ember" (dark). tests/test_contrast.py checks every theme against WCAG 2.2.
    "theme": {
        "bg_start": "#0c111d", "bg_mid": "#1f2233", "bg_end": "#352730",   # window gradient
        "glow1": "#4377c7", "glow2": "#85516f",                            # soft glows over it
        "surface": "#202332", "card_bottom": "#2d3043",                     # cards and panels
        "card_hover_top": "#26293b", "card_hover_bottom": "#343851",
        "border": "#6075d2", "border_hover": "#8a9be3",
        "text": "#f8fafc", "text_muted": "#a9b5c6", "text_soft": "#cad5e2", "text_body": "#e1e7ef",
        "link": "#7bb0f4", "ok": "#72caad", "danger": "#ffb4a2",
        "accent": "#e79440", "accent_deep": "#e3801c", "on_accent": "#131935",  # main buttons, warnings
    },
    "system": {
        "data_mount": "/mnt/loopdata",
        "data_label": "LOOPDATA",
        "usb_model": "",  # optional: only format a USB drive whose model contains this text
    },
}

_cache = None


def _paths(name):
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = [os.environ.get("LOOP_CONFIG_DIR"), here, "/etc/loop", APP_DIR]
    dirs = list(dict.fromkeys(d for d in dirs if d))
    return [os.path.join(d, name) for d in dirs if d]


def _merge(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def _read(name):
    for path in _paths(name):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as e:
            print(f"loop_profile: ignoring unreadable {path}: {e}", file=sys.stderr)
            return {}
    return {}


PROFILES_DIRS = ("/usr/share/loop/profiles", os.path.join(CODE_DIR, "..", "profiles"))


def base_profile_dir(name):
    """Folder of a packaged profile (e.g. "default"), or None."""
    for d in PROFILES_DIRS:
        path = os.path.join(d, name)
        if name and "/" not in name and os.path.isfile(os.path.join(path, "profile.json")):
            return path
    return None


def load(refresh=False):
    """The merged configuration: defaults <- packaged base profile <- profile.json <- site.json.
    A profile.json with "basedOn": "<name>" layers its own values over that packaged profile, so package
    upgrades deliver profile improvements while local changes (setup wizard, Settings) are kept."""
    global _cache
    if _cache is None or refresh:
        cfg = copy.deepcopy(DEFAULTS)
        local = _read("profile.json")
        base = base_profile_dir(local.get("basedOn", ""))
        if base:
            try:
                with open(os.path.join(base, "profile.json"), encoding="utf-8") as f:
                    _merge(cfg, json.load(f))
            except (OSError, ValueError):
                pass
        _merge(cfg, local)
        _merge(cfg, _read("site.json"))
        _cache = cfg
    return _cache


def get(path, default=None):
    node = load()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def fill(text):
    """Replace {{dotted.key}} placeholders with configured values."""
    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", lambda m: str(get(m.group(1), m.group(0))), text)


ROTATIONS = (0, 90, 180, 270)
ORIENTATION_ROTATE = {"landscape": 0, "portrait-cw": 90, "landscape-flipped": 180, "portrait-ccw": 270}
IDLE_DIR = os.path.join(STATE_DIR, "idle")  # idle videos made by loop-idle-video


def display(hostname=None):
    """This display's settings: orientation, rotate and label. The Pi's output always stays landscape; rotate
    (degrees clockwise) is how far content is pre-rotated to suit the way the TV is mounted. It defaults from
    the orientation (portrait-cw: 90)."""
    host = hostname or socket.gethostname()
    d = dict(get("displays", {}).get(host, {}))
    d.setdefault("orientation", "landscape")
    d.setdefault("label", host)
    try:
        rot = int(d.get("rotate", ORIENTATION_ROTATE.get(d["orientation"], 0))) % 360
    except (TypeError, ValueError):
        rot = 0
    d["rotate"] = rot if rot in ROTATIONS else 0
    return d


def idle_source(rotate):
    """The idle still to make this display's idle video from: portrait art for a display turned 90 or 270
    degrees (when there is some), otherwise the landscape art. A picture given to loop-setup (in
    /etc/loop/branding) always comes before the packaged profile's art."""
    names = (["idle-screen-portrait.png", "idle-screen-portrait.jpg"] if rotate in (90, 270) else []) + \
            ["idle-screen.png", "idle-screen.jpg", "idle.png"]
    own = [d for d in (os.environ.get("LOOP_BRANDING_DIR"), "/etc/loop/branding") if d]
    for dirs in (own, _branding_dirs()):  # the organization's own pictures before any packaged ones
        for n in names:
            for d in dirs:
                if os.path.isfile(os.path.join(d, n)):
                    return os.path.join(d, n)
    return None


def idle_generated(rotate, ext="mp4"):
    return os.path.join(IDLE_DIR, f"idle-screen-r{rotate}.{ext}")


def _branding_dirs():
    base = base_profile_dir(get("basedOn", ""))
    return [d for d in (os.environ.get("LOOP_BRANDING_DIR"), "/etc/loop/branding", base, APP_DIR, CODE_DIR,
                        "/usr/share/loop/assets", "/usr/share/loop/profiles/default",
                        os.path.join(CODE_DIR, "..", "assets", "temple"),
                        os.path.join(CODE_DIR, "..", "profiles", "default")) if d]


def asset(name):
    """Path of a branding file (logo, icon, idle art), or None. The organization's branding in
    /etc/loop/branding comes first; LOOP's own assets (the Temple Consulting logo) come last."""
    for d in _branding_dirs():
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    return None


def idle_media(hostname=None):
    """The idle screen for this display, always a video when one exists (a still picture costs VLC far more
    CPU and heat): the video loop-idle-video made for this display's rotation, then the profile's own
    pre-rendered videos, then a still picture as the last resort."""
    rot = display(hostname)["rotate"]
    made = idle_generated(rot)
    if os.path.isfile(made):
        return made
    if rot == 90:
        names = ["idle-screen-rotated.mp4", "idle-screen-rotated.png"]
    elif rot == 0:
        names = ["idle-screen.mp4", "idle-screen.png", "idle.mp4", "idle.png"]
    else:
        names = []
    names += ["idle-screen.mp4", "idle-screen.png", "idle.mp4", "idle.png"]
    for n in names:
        path = asset(n)
        if path:
            return path
    return os.path.join(APP_DIR, "idle.png")


def backup_video():
    for path in (os.path.join(STATE_DIR, "backup.mp4"), os.path.join(APP_DIR, "backup.mp4")):
        if os.path.isfile(path):
            return path
    return os.path.join(STATE_DIR, "backup.mp4")


def player_service():
    """The player's user service: loop-player (package) or display-player (legacy scripts)."""
    return "loop-player.service" if os.path.exists("/usr/lib/systemd/user/loop-player.service") \
        else "display-player.service"


def history_service():
    return "loop-history.service" if os.path.exists("/usr/lib/systemd/user/loop-history.service") \
        else "burnin-logger.service"


def theme():
    return dict(get("theme", {}))


def themed_css(template):
    """Fill @token@ colors in a style sheet from the profile's theme (bytes in, bytes out)."""
    t = theme()
    text = template.decode() if isinstance(template, bytes) else template
    text = re.sub(r"@(\w+)@", lambda m: t.get(m.group(1), m.group(0)), text)
    return text.encode()


def data_mount():
    return get("system.data_mount", DEFAULTS["system"]["data_mount"])


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "get":
        value = get(sys.argv[2], "")
        print(json.dumps(value) if isinstance(value, (dict, list)) else value)
    elif len(sys.argv) >= 2 and sys.argv[1] == "wallpaper":
        # The idle art as a still picture for the desktop background, rotated like the idle video.
        rot = display()["rotate"]
        made = idle_generated(rot, "png")
        if os.path.isfile(made):
            print(made)
        else:
            for n in (["idle-screen-rotated.png"] if rot == 90 else []) + ["idle-screen.png", "idle.png"]:
                if asset(n):
                    print(asset(n))
                    break
    elif len(sys.argv) >= 2 and sys.argv[1] == "asset":
        print(asset(sys.argv[2]) or "")
    elif len(sys.argv) >= 2 and sys.argv[1] == "rotate":
        print(display(sys.argv[2] if len(sys.argv) > 2 else None)["rotate"])
    elif len(sys.argv) >= 2 and sys.argv[1] == "orientation":
        print(display(sys.argv[2] if len(sys.argv) > 2 else None)["orientation"])
    else:
        print(json.dumps(load(), indent=2))
