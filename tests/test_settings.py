# SPDX-License-Identifier: AGPL-3.0-or-later
"""loop_settings: the setup wizard's and Settings' checks, the files they write, and root's check of them.
Run: python3 tests/test_settings.py
"""
import json
import os
import shutil
import socket
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ["LOOP_CONFIG_DIR"] = tempfile.mkdtemp()
import loop_settings as S  # noqa: E402

fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


v = S.current()
good = dict(v, **{"content.library_url": "https://videos.example.org/share"})
check(S.validate(good) == {}, "defaults plus a library link are valid")
check("content.library_url" in S.validate(v), "the library link is required")
bad = dict(good, **{"content.library_url": "http://insecure.example", "identity.contact": "",
                    "identity.launcher_name": "x" * 30, "display.rotate": 45, "colors.desktop": "#f0f0f0",
                    "theme.accent": "#1a2b4c", "content.keep_videos": 99, "identity.organization": "<b>"})
errs = S.validate(bad)
for key in ("content.library_url", "identity.contact", "identity.launcher_name", "display.rotate", "colors.desktop",
            "theme.accent", "content.keep_videos", "identity.organization"):
    check(key in errs, f"rejects a bad {key}: {errs.get(key)}")

for accent in ("#ffdf20", "#7ad0ff", "#e79440", "#ffffff"):
    t = S.button_theme(S.base_config("default")["theme"], accent)
    probs = [p for p in S.theme_problems(t) if p.startswith(("accent", "on_accent"))]
    check(not probs and S.validate(dict(good, **{"theme.accent": accent})) == {},
          f"button color {accent}: readable text chosen ({t['on_accent']})")

# Readable colors, automatically: every color either passes or comes with a passing shade of the same hue.
import random  # noqa: E402
random.seed(7)
misses = []
for base in ("default", "wth"):
    th = S.base_config(base)["theme"]
    for _ in range(300):
        hx = "#%06x" % random.randrange(0x1000000)
        fix = S.readable_suggestion("theme.accent", hx, base)
        if not S._button_ok(th, fix or hx):
            misses.append(("button", base, hx))
        for key in ("colors.desktop", "colors.accent"):
            if S.ratio(S.readable_suggestion(key, hx) or hx, "#ffffff") < 4.5:
                misses.append((key, hx))
check(not misses, f"600 random colors: each passes or gets a readable shade ({len(misses)} misses)")
_l, c0, h0 = S.to_oklch("#2a9d8f")
_l, c1, h1 = S.to_oklch(S.readable_suggestion("theme.accent", "#2a9d8f", "default"))
check(abs(h0 - h1) < 0.05, "the suggested shade keeps the color's hue")
t = S.button_theme(S.base_config("default")["theme"], "#e79440")
check(t["on_accent"] == S.tinted_dark("#e79440") and S.ratio(t["on_accent"], t["accent_deep"]) >= 4.5,
      f"button text is a dark shade of the button's own hue when it passes ({t['on_accent']})")
err = S.validate(dict(good, **{"theme.accent": "#2a9d8f", "colors.accent": "#7accc8"}))
check("Try #" in err.get("theme.accent", "") and "Try #" in err.get("colors.accent", ""),
      f"problems name the readable shade: {err.get('colors.accent')}")

# A two-tone window background of your own.
g = dict(good, **{"theme.bg_start": "#12233f", "theme.bg_end": "#2b1636"})
check(S.validate(g) == {}, "a dark two-tone background is accepted")
prof, _site = S.build(g, {})
check(prof["theme"]["bg_start"] == "#12233f" and prof["theme"]["bg_end"] == "#2b1636" and "bg_mid" in prof["theme"]
      and "surface" in prof["theme"] and not S.theme_problems(S.full_theme(g)),
      "the gradient and the colors that follow from it are saved, and pass WCAG")
light = dict(good, **{"theme.bg_start": "#9fb4d8"})
err = S.validate(light).get("theme.bg_start", "")
fix = S.readable_suggestion("theme.bg_start", "#9fb4d8", "default", light)
check("Try #" in err and fix and S._background_ok(S.full_theme(dict(light, **{"theme.bg_start": fix}))),
      f"a light background is caught and gets a readable shade ({fix})")
unchanged, _s = S.build(good, {})
check("theme" not in unchanged, "the profile's own background is not written when unchanged")

host = socket.gethostname()
vals = dict(good, **{"identity.organization": "Example Pantry", "display.rotate": 90, "display.label": "Window",
                     "theme.accent": "#7ad0ff", "base": "default"})
other = {"displays": {"another-pi": {"label": "Lobby", "rotate": 0}}, "system": {"data_label": "VIDEOS"}}
profile, site = S.build(vals, other)
check(profile.get("basedOn") == "default" and profile["identity"] == {"organization": "Example Pantry"}
      and set(profile["theme"]) == {"accent", "accent_deep", "on_accent"} and "content" not in profile,
      "profile.json keeps only what differs from the base profile")
check(site["content"]["library_url"] == "https://videos.example.org/share" and
      site["displays"][host] == {"label": "Window", "rotate": 90, "orientation": "portrait-cw"} and
      site["displays"]["another-pi"]["label"] == "Lobby" and site["system"]["data_label"] == "VIDEOS",
      "site.json: private settings and this display, other displays and settings kept")

# Root's check of a settings folder
d = tempfile.mkdtemp()
json.dump(profile, open(os.path.join(d, "profile.json"), "w"))
json.dump(site, open(os.path.join(d, "site.json"), "w"))
shutil.copy(os.path.join(ROOT, "profiles", "default", "idle-screen.png"), os.path.join(d, "idle-screen.png"))
check(S.check_dir(d) == [], f"a good settings folder passes {S.check_dir(d)}")
open(os.path.join(d, "staff-icon.png"), "w").write("not a picture")
check(any("staff" in p or "file.icon" in p for p in S.check_dir(d)), "a fake picture is refused")
os.remove(os.path.join(d, "staff-icon.png"))
os.symlink("/etc/hosts", os.path.join(d, "logo-white.png"))
check(any("file.logo" in p for p in S.check_dir(d)), "a symbolic link is refused")
os.remove(os.path.join(d, "logo-white.png"))
open(os.path.join(d, S.RESET_MARK), "w").close()
check(S.check_dir(d) == [], "the use-the-profile's-pictures request is allowed")
os.remove(os.path.join(d, S.RESET_MARK))
open(os.path.join(d, "evil.sh"), "w").write("#!/bin/sh\n")
check(any("unexpected" in p for p in S.check_dir(d)), "unexpected files are refused")
os.remove(os.path.join(d, "evil.sh"))
json.dump(dict(profile, theme={"accent": "#111111"}), open(os.path.join(d, "profile.json"), "w"))
check(any(p.startswith("theme") for p in S.check_dir(d)), "an unreadable theme is refused")

print("all passed" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
