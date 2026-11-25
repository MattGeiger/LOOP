#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Remember what LOOP changes in the desktop user's settings, so removing LOOP can put them back.

loop-user-setup and the scripts it runs call this before and after each change; `loop-user-setup --undo`
(run for each display user when the package is removed) calls undo(). Run as the desktop user.

The record lives in ~/.local/state/loop: the first time LOOP touches a file it keeps the original (or notes
that there was none), and after each change it notes what LOOP wrote. Undo puts an item back only if it still
holds what LOOP wrote. Anything someone changed afterwards is left alone and reported.

  loop_undo.py snapshot FILE...           keep FILE's original (first time only)
  loop_undo.py wrote FILE...              note what LOOP wrote to FILE
  loop_undo.py keys FILE KEY...           keep the original key=value lines (first time only)
  loop_undo.py wrote-keys FILE KEY...     note the values LOOP wrote
  loop_undo.py panel FILE                 keep / note the taskbar launchers line (call before and after)
  loop_undo.py undo [--legacy]            put everything back; --legacy also cleans up a LOOP setup made
                                          before this record existed
"""
import hashlib
import json
import os
import re
import shutil
import sys

HOME = os.path.expanduser("~")
STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local", "state"), "loop")
ORIG = os.path.join(STATE, "original")
RECORD = os.path.join(STATE, "undo.json")
ABSENT = None
LAUNCHER = "loop-staff-tools"


def _load():
    try:
        with open(RECORD) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"files": {}, "keys": {}, "panel": {}, "created": []}


def _save(rec):
    os.makedirs(STATE, exist_ok=True)
    tmp = RECORD + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=1)
    os.replace(tmp, RECORD)


def _rel(path):
    path = os.path.abspath(os.path.expanduser(path))
    return os.path.relpath(path, HOME) if path.startswith(HOME + os.sep) else path


def _abs(rel):
    return rel if os.path.isabs(rel) else os.path.join(HOME, rel)


def _sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------- whole files
def snapshot(*paths):
    rec = _load()
    for p in paths:
        rel = _rel(p)
        entry = rec["files"].setdefault(rel, {})
        if "original" in entry:
            continue
        if os.path.isfile(_abs(rel)):
            dest = os.path.join(ORIG, rel.lstrip("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(_abs(rel), dest)
            entry["original"] = "kept"
        else:
            entry["original"] = ABSENT
    _save(rec)


def wrote(*paths):
    rec = _load()
    for p in paths:
        rec["files"].setdefault(_rel(p), {"original": ABSENT})["wrote"] = _sha(p)
    _save(rec)


# ---------------------------------------------------------------- key=value lines (VLC's vlcrc)
def _read_keys(path, keys):
    vals = {k: ABSENT for k in keys}
    try:
        for line in open(path):
            m = re.match(r"^([\w-]+)=(.*)$", line.rstrip("\n"))
            if m and m.group(1) in vals:
                vals[m.group(1)] = m.group(2)
    except OSError:
        pass
    return vals


def keys(path, *names):
    rec = _load()
    entry = rec["keys"].setdefault(_rel(path), {"original": {}, "wrote": {}})
    for k, v in _read_keys(path, names).items():
        entry["original"].setdefault(k, v)
    _save(rec)


def wrote_keys(path, *names):
    rec = _load()
    entry = rec["keys"].setdefault(_rel(path), {"original": {}, "wrote": {}})
    entry["wrote"].update(_read_keys(path, names))
    _save(rec)


def _undo_keys(rel, entry, report):
    path = _abs(rel)
    if not os.path.isfile(path):
        return
    lines = open(path).read().splitlines()
    changed, kept = False, []
    for k, loop_value in entry.get("wrote", {}).items():
        orig = entry.get("original", {}).get(k, ABSENT)
        for i, line in enumerate(lines):
            m = re.match(r"^([\w-]+)=(.*)$", line)
            if not m or m.group(1) != k:
                continue
            if m.group(2) != loop_value:
                kept.append(k)
            elif orig is ABSENT:
                lines[i] = f"#{k}="  # back to VLC's default
                changed = True
            elif orig != loop_value:
                lines[i] = f"{k}={orig}"
                changed = True
            break
    if changed:
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        report.append(f"restored {rel}")
    if kept:
        report.append(f"left {', '.join(kept)} in {rel} (changed after LOOP set it)")


# ---------------------------------------------------------------- taskbar launchers (wf-panel-pi.ini)
def _launchers(path):
    section = None
    try:
        for line in open(path):
            line = line.strip()
            if line.startswith("["):
                section = line
            elif section == "[panel]" and line.startswith("launchers="):
                return line.split("=", 1)[1]
    except OSError:
        pass
    return ABSENT


def panel(path):
    """First call: keep the original launchers line. Every call: note the current one as LOOP's."""
    rec = _load()
    entry = rec["panel"].setdefault(_rel(path), {})
    if "original" not in entry:
        entry["original"] = _launchers(path)
    else:
        entry["wrote"] = _launchers(path)
    _save(rec)


def _undo_panel(rel, entry, report):
    path = _abs(rel)
    cur = _launchers(path)
    if cur is ABSENT:
        return
    if cur == entry.get("wrote"):
        new = entry.get("original")
    else:
        new = " ".join(x for x in cur.split() if x != LAUNCHER)
    out, section, done = [], None, False
    for line in open(path).read().splitlines():
        if line.strip().startswith("["):
            section = line.strip()
        if section == "[panel]" and line.strip().startswith("launchers=") and not done:
            done = True
            if new is not ABSENT:
                out.append(f"launchers={new}")
            continue
        out.append(line)
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    report.append(f"taskbar launchers restored ({new if new is not ABSENT else 'Raspberry Pi OS default'})")


# ---------------------------------------------------------------- Chromium (it rewrites its own files)
def chromium_snapshot(prefs_path, bookmarks_path, first_run_path):
    """Before setup_chromium changes anything: keep the original download settings, bookmarks bar and
    whether Chromium's first-run marker existed (first time only)."""
    rec = _load()
    if "chromium" in rec:
        return
    prefs = {}
    try:
        prefs = json.load(open(prefs_path))
    except (OSError, ValueError):
        pass
    bar = None
    try:
        bar = json.load(open(bookmarks_path))["roots"]["bookmark_bar"]["children"]
    except (OSError, ValueError, KeyError):
        pass
    rec["chromium"] = {
        "prefs": _rel(prefs_path), "bookmarks": _rel(bookmarks_path), "first_run": _rel(first_run_path),
        "first_run_existed": os.path.exists(first_run_path),
        "prefs_existed": os.path.exists(prefs_path), "bookmarks_existed": os.path.exists(bookmarks_path),
        "root_existed": os.path.exists(os.path.dirname(first_run_path)),
        "welcome": prefs.get("browser", {}).get("has_seen_welcome_page", ABSENT),
        "download": {k: prefs.get("download", {}).get(k, ABSENT)
                     for k in ("default_directory", "prompt_for_download", "directory_upgrade")},
        "savefile": prefs.get("savefile", {}).get("default_directory", ABSENT),
        "show_bar": prefs.get("bookmark_bar", {}).get("show_on_all_tabs", ABSENT),
        "bar": bar,
    }
    _save(rec)


def chromium_wrote(drop, url, name):
    rec = _load()
    rec.setdefault("chromium", {}).update(loop={"drop": drop, "url": url, "name": name})
    _save(rec)


def _undo_chromium(c, report, legacy_loop=None):
    import subprocess
    if subprocess.run(["pgrep", "-x", "chromium"], capture_output=True).returncode == 0:
        report.append("Chromium is open: its bookmark and download folder were not changed")
        return False
    loop = c.get("loop") or legacy_loop or {}
    prefs_path = _abs(c.get("prefs", ".config/chromium/Default/Preferences"))
    try:
        prefs = json.load(open(prefs_path))
    except (OSError, ValueError):
        prefs = None
    if prefs is not None:
        dl = prefs.setdefault("download", {})
        if loop.get("drop") and dl.get("default_directory") == loop["drop"]:
            for k, v in c.get("download", {}).items():
                if v is ABSENT:
                    dl.pop(k, None)
                else:
                    dl[k] = v
            sf = prefs.setdefault("savefile", {})
            if c.get("savefile") is ABSENT:
                sf.pop("default_directory", None)
            elif "savefile" in c:
                sf["default_directory"] = c["savefile"]
            if c.get("show_bar", ABSENT) is ABSENT:
                prefs.get("bookmark_bar", {}).pop("show_on_all_tabs", None)
            else:
                prefs.setdefault("bookmark_bar", {})["show_on_all_tabs"] = c["show_bar"]
            if c.get("welcome", ABSENT) is ABSENT and "loop" in c:
                prefs.get("browser", {}).pop("has_seen_welcome_page", None)
            prefs = {k: v for k, v in prefs.items() if v != {}}
            if not prefs and c.get("prefs_existed") is False:
                os.remove(prefs_path)  # LOOP made it and Chromium never added to it
            else:
                with open(prefs_path, "w") as f:
                    json.dump(prefs, f)
            report.append("Chromium download folder restored")
    bm_path = _abs(c.get("bookmarks", ".config/chromium/Default/Bookmarks"))
    try:
        bm = json.load(open(bm_path))
        bar = bm["roots"]["bookmark_bar"]
    except (OSError, ValueError, KeyError):
        bar = None
    if bar is not None and loop.get("url"):
        mine = [b for b in bar.get("children", []) if b.get("type") == "url" and b.get("url") == loop["url"]]
        if mine:
            rest = [b for b in bar["children"] if b not in mine]
            bar["children"] = rest if rest or c.get("bar") is None else c["bar"]
            bm.pop("checksum", None)  # Chromium recomputes it
            others = [b for k, r in bm["roots"].items() if k != "bookmark_bar" for b in r.get("children", [])]
            if not bar["children"] and not others and c.get("bookmarks_existed") is False:
                os.remove(bm_path)  # LOOP made it
            else:
                with open(bm_path, "w") as f:
                    json.dump(bm, f, indent=3)
            report.append("Chromium bookmark removed" + (" (earlier bookmarks restored)" if not rest and c.get("bar")
                                                         else ""))
    fr = _abs(c.get("first_run", ".config/chromium/First Run"))
    if c.get("first_run_existed") is False and os.path.exists(fr):
        os.remove(fr)
    root = os.path.dirname(fr)
    if c.get("root_existed") is False and os.path.isdir(root):
        for d, _subdirs, _files in sorted(os.walk(root), key=lambda x: -len(x[0])):  # empty folders LOOP made
            if not os.listdir(d):
                os.rmdir(d)
    return True


# ---------------------------------------------------------------- undo
LEGACY_FILES = [".config/pcmanfm/default/desktop-items-NOOP-1.conf", ".config/pcmanfm/default/desktop-items-HDMI-A-1.conf",
                ".config/pcmanfm/default/desktop-items-HDMI-A-2.conf", ".config/labwc/themerc-override",
                ".config/gtk-3.0/gtk.css"]
LEGACY_MARKS = ("[loop-staff-tools.desktop]", "LOOP display branding", "window.active.title.bg.color")
LEGACY_VLC = {"extraintf": "http", "http-host": "127.0.0.1", "http-port": "8080", "loop": "1"}


def _legacy_record(rec):
    """Build a record for a LOOP setup made before the record existed. Its scripts kept timestamped copies
    (<file>.bak-loop-<time>); the oldest is the original. Files LOOP made from nothing are removed."""
    import glob
    for rel in LEGACY_FILES:
        path = _abs(rel)
        if rel in rec["files"] or not os.path.isfile(path):
            continue
        text = open(path).read()
        if not any(m in text for m in LEGACY_MARKS):
            continue
        baks = sorted(glob.glob(path + ".bak-loop-*"))
        entry = {"original": ABSENT, "wrote": _sha(path)}
        if baks and not any(m in open(baks[0]).read() for m in LEGACY_MARKS):
            dest = os.path.join(ORIG, rel.lstrip("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(baks[0], dest)
            entry["original"] = "kept"
        rec["files"][rel] = entry
    vlc = ".config/vlc/vlcrc"
    if vlc not in rec["keys"]:
        cur = _read_keys(_abs(vlc), list(LEGACY_VLC) + ["http-password"])
        rec["keys"][vlc] = {"original": {k: ABSENT for k in cur},
                            "wrote": {k: v for k, v in cur.items()
                                      if v is not ABSENT and (k == "http-password" or LEGACY_VLC.get(k) == v)}}
    # LOOP's exact launcher set goes entirely, so Raspberry Pi OS's own default taskbar returns
    rec["panel"].setdefault(".config/wf-panel-pi/wf-panel-pi.ini",
                            {"original": ABSENT, "wrote": "loop-staff-tools x-www-browser pcmanfm"})


def undo(legacy=False):
    rec, report = _load(), []
    if legacy:  # set up before LOOP kept a record
        _legacy_record(rec)
    for rel, entry in rec["files"].items():
        path = _abs(rel)
        if not os.path.exists(path) and entry.get("original") is ABSENT:
            continue
        if entry.get("wrote") and _sha(path) != entry["wrote"]:
            report.append(f"left {rel} (changed after LOOP set it)")
            continue
        if entry.get("original") == "kept":
            shutil.copy2(os.path.join(ORIG, rel.lstrip("/")), path)
            report.append(f"restored {rel}")
        elif os.path.exists(path):
            os.remove(path)
            report.append(f"removed {rel}")
            if rel.startswith(".local/share/themes/"):  # the theme folders LOOP made, if now empty
                d, top = os.path.dirname(path), _abs(".local/share/themes")
                while d.startswith(top + "/") and os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
                    d = os.path.dirname(d)
    for rel, entry in rec["keys"].items():
        _undo_keys(rel, entry, report)
    for rel, entry in rec["panel"].items():
        _undo_panel(rel, entry, report)
    chromium_done = True
    if "chromium" in rec or legacy:
        legacy_loop = None
        if legacy and "chromium" not in rec:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            try:
                import loop_profile
                legacy_loop = {"drop": os.path.join(loop_profile.data_mount(), "videos"),
                               "url": loop_profile.get("content.library_url")}
            except Exception:
                legacy_loop = None
        if "chromium" in rec or (legacy_loop and legacy_loop.get("url")):
            chromium_done = _undo_chromium(rec.get("chromium", {}), report, legacy_loop)
            rec.setdefault("chromium", {})
    mime = os.path.join(HOME, ".config", "mimeapps.list")
    if os.path.isfile(mime):
        lines = open(mime).read().splitlines()
        keep = [ln for ln in lines if "x-scheme-handler/loop-staff-tools" not in ln]
        if keep != lines:
            with open(mime, "w") as f:
                f.write("\n".join(keep) + "\n")
    if legacy:  # the old scripts' timestamped copies
        import glob
        chromium = [".config/chromium/Default/Preferences", ".config/chromium/Default/Bookmarks"]
        for rel in LEGACY_FILES + (chromium if chromium_done and "chromium" in rec else []):
            for bak in glob.glob(_abs(rel) + ".bak-loop-*"):
                os.remove(bak)
        report.append("old .bak-loop copies removed")
    for name in ("loop-player", "loop-history"):
        link = os.path.join(HOME, ".config", "systemd", "user", "default.target.wants", f"{name}.service")
        if os.path.lexists(link):
            os.remove(link)
    desktop = os.path.join(HOME, "Desktop", "loop-staff-tools.desktop")
    if os.path.exists(desktop):
        os.remove(desktop)
    report.append("Staff Tools icon, link handler and services removed")
    if chromium_done:
        shutil.rmtree(STATE, ignore_errors=True)
    else:
        rec.pop("files"); rec.pop("keys"); rec.pop("panel")  # only Chromium is left to do
        rec.update(files={}, keys={}, panel={})
        _save(rec)
    for line in report:
        print("loop-undo: " + line)
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "snapshot":
        snapshot(*args)
    elif cmd == "wrote":
        wrote(*args)
    elif cmd == "keys":
        keys(args[0], *args[1:])
    elif cmd == "wrote-keys":
        wrote_keys(args[0], *args[1:])
    elif cmd == "panel":
        panel(args[0])
    elif cmd == "undo":
        return undo("--legacy" in args)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
