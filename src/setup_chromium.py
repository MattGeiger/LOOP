#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Set up Chromium on a LOOP display Pi for the staff video-update workflow.

- Downloads go straight to the drop folder (<data mount>/videos), no "Save as" prompt.
- Bookmarks bar shown, with exactly one bookmark: the video library from site.json
  (content.library_url, named content.bookmark_name). Any other bookmarks on the bar are removed.
- Works on an existing profile or creates a fresh one (marking first run as done, so
  Chromium doesn't import the Raspberry Pi default bookmarks).
Run as the desktop user while Chromium is closed. The first time, the original settings are kept
(loop_undo.py) so removing LOOP puts them back.
"""
import json
import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_profile  # noqa: E402
import loop_undo  # noqa: E402

ROOT = os.path.expanduser("~/.config/chromium")
PROFILE = os.path.join(ROOT, "Default")
DROP = os.path.join(loop_profile.data_mount(), "videos")
BOOKMARK_NAME = loop_profile.get("content.bookmark_name")
BOOKMARK_URL = loop_profile.get("content.library_url")
if not BOOKMARK_URL:
    sys.exit("ABORT: no video library set (content.library_url in site.json)")

if subprocess.run(["pgrep", "-x", "chromium"], capture_output=True).returncode == 0:
    sys.exit("ABORT: close Chromium first (it overwrites its settings on exit)")
prefs_path = os.path.join(PROFILE, "Preferences")
bm_path = os.path.join(PROFILE, "Bookmarks")
loop_undo.chromium_snapshot(prefs_path, bm_path, os.path.join(ROOT, "First Run"))  # before making any folder
os.makedirs(PROFILE, exist_ok=True)
open(os.path.join(ROOT, "First Run"), "a").close()  # skip first-run imports and welcome pages

# Preferences: download folder + bookmarks bar
prefs = {}
if os.path.exists(prefs_path):
    with open(prefs_path) as f:
        prefs = json.load(f)
prefs.setdefault("download", {}).update(default_directory=DROP, prompt_for_download=False,
                                        directory_upgrade=True)
prefs.setdefault("savefile", {})["default_directory"] = DROP
prefs.setdefault("bookmark_bar", {})["show_on_all_tabs"] = True
prefs.setdefault("browser", {})["has_seen_welcome_page"] = True
with open(prefs_path, "w") as f:
    json.dump(prefs, f)

# Bookmarks: the bar holds only the video library
now = str(int((time.time() + 11644473600) * 1_000_000))  # Chromium time: microseconds since 1601


def folder(gid, i, name, children=()):
    return {"children": list(children), "date_added": now, "date_modified": "0",
            "guid": gid, "id": i, "name": name, "type": "folder"}


bm = {"roots": {
    "bookmark_bar": folder("0bc5d13f-2cba-5d74-951f-3f233fe6c908", "1", "Bookmarks bar", [
        {"date_added": now, "guid": str(uuid.uuid4()), "id": "4",
         "name": BOOKMARK_NAME, "type": "url", "url": BOOKMARK_URL}]),
    "other": folder("82b081ec-3dd3-529c-8475-ab6c344590dd", "2", "Other bookmarks"),
    "synced": folder("4cf2e351-0e85-532b-bb37-df045d8f8d0f", "3", "Mobile bookmarks")},
    "version": 1}
with open(bm_path, "w") as f:
    json.dump(bm, f, indent=3)

loop_undo.chromium_wrote(DROP, BOOKMARK_URL, BOOKMARK_NAME)
print("downloads ->", prefs["download"]["default_directory"],
      "| prompt:", prefs["download"]["prompt_for_download"])
print("bookmarks bar:", [c["name"] for c in bm["roots"]["bookmark_bar"]["children"]])
print("CHROMIUM_SETUP_DONE")
