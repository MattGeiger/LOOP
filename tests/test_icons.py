# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""LOOP's icons stay one system (docs/DESIGN_LANGUAGE.md):
  - every icon in the table is bundled, pinned to a Lucide release, and every bundled icon is used
  - the design document names every icon in the table, so the meanings are written down
  - every button label in the windows' code has an icon in the table
  - Lucide's licence ships with the icons
Run: python3 tests/test_icons.py"""
import ast
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "src")
fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


# The table, read without GTK.
tree = ast.parse(open(os.path.join(SRC, "ui_icons.py")).read())
consts = {t.id: node.value for node in tree.body if isinstance(node, ast.Assign)
          for t in node.targets if isinstance(t, ast.Name)}
ICONS = ast.literal_eval(consts["ICONS"])
BUSY = ast.literal_eval(consts["BUSY"])
PREFIXES = ast.literal_eval(consts["PREFIXES"])
used = set(ICONS.values()) | {BUSY}

icon_dir = os.path.join(SRC, "icons")
bundled = {f[:-4] for f in os.listdir(icon_dir) if f.endswith(".svg")}
check(not (used - bundled), "every icon in the table is bundled" + (f": missing {sorted(used - bundled)}" if used - bundled else ""))
check(not (bundled - used), "every bundled icon is used" + (f": unused {sorted(bundled - used)}" if bundled - used else ""))
unpinned = [n for n in bundled if not re.search(r"@license lucide-static v\d+\.\d+\.\d+ - ISC",
                                                 open(os.path.join(icon_dir, n + ".svg")).read(200))]
check(not unpinned, "every icon is pinned to a Lucide release" + (f": {unpinned}" if unpinned else ""))
check(os.path.isfile(os.path.join(icon_dir, "LICENSE")) and "ISC License" in open(os.path.join(icon_dir, "LICENSE")).read(),
      "Lucide's licence is bundled")

doc = open(os.path.join(ROOT, "docs", "DESIGN_LANGUAGE.md")).read()
undocumented = sorted(n for n in used if f"`{n}`" not in doc)
check(not undocumented, "the design language names every icon" + (f": missing {undocumented}" if undocumented else ""))


def has_icon(label):
    t = label.strip().rstrip("…").strip()
    return t in ICONS or any(t.startswith(p) for p in PREFIXES)


# Button labels in the admin windows: ("Label", callback, "primary"|"ghost", busy).
labels = set()
for f in ("staff_admin.py", "settings_ui.py"):
    s = open(os.path.join(SRC, f)).read()
    labels |= set(re.findall(r'\(f?"([^"{]{2,60})[^"]*", [^()]*?, "(?:primary|ghost)"', s))
labels |= {"Get a new video", "Open videos folder", "Show idle screen", "Restart video", "Display status",
           "Performance history", "Update Software", "Start fullscreen playback", "Setup & Burn-in",
           "Help", "About", "Settings", "Source Code on GitHub", "Close"}
missing = sorted(l for l in labels if not has_icon(l))
check(not missing, f"{len(labels)} button labels all have an icon" + (f": missing {missing}" if missing else ""))

sys.exit(1 if fails else 0)
