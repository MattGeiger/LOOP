# SPDX-License-Identifier: AGPL-3.0-or-later
"""loop_undo: removing LOOP puts the desktop user's settings back, and leaves what someone changed since.

Runs the record-and-undo steps the setup scripts use, in a throwaway home folder.
Run: python3 tests/test_undo.py
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
UNDO = os.path.join(ROOT, "src", "loop_undo.py")
fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def run(home, *args):
    env = dict(os.environ, HOME=home, XDG_STATE_HOME=os.path.join(home, ".local", "state"),
               PATH="/usr/bin:/bin")  # no Chromium running here
    return subprocess.run([sys.executable, UNDO, *args], env=env, capture_output=True, text=True, check=True).stdout


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(path):
    return open(path).read() if os.path.exists(path) else None


def fresh_setup():
    """A desktop user with their own settings, then LOOP's setup steps (as the scripts run them)."""
    home = tempfile.mkdtemp()
    c = lambda p: os.path.join(home, p)  # noqa: E731
    vlcrc, panel = c(".config/vlc/vlcrc"), c(".config/wf-panel-pi/wf-panel-pi.ini")
    gtk, themerc = c(".config/gtk-3.0/gtk.css"), c(".config/labwc/themerc-override")
    theme = c(".local/share/themes/PiXtrix/gtk-3.0/gtk.css")
    prefs, bms = c(".config/chromium/Default/Preferences"), c(".config/chromium/Default/Bookmarks")
    write(vlcrc, "[core]\n#extraintf=\nloop=0\nvolume=200\n")
    write(panel, "[panel]\nlaunchers=x-www-browser lxterminal\nicon_size=36\n")
    write(gtk, "/* the user's own */\n")
    write(prefs, json.dumps({"download": {"default_directory": "/home/pi/Downloads"}, "homepage": "x"}))
    write(bms, json.dumps({"roots": {"bookmark_bar": {"children": [{"type": "url", "name": "News",
                                                                      "url": "https://news.example"}]}}}))
    # loop-user-setup: VLC keys and the taskbar
    run(home, "keys", vlcrc, "extraintf", "http-host", "loop")
    write(vlcrc, "[core]\nextraintf=http\nloop=1\nvolume=200\nhttp-host=127.0.0.1\n")
    run(home, "wrote-keys", vlcrc, "extraintf", "http-host", "loop")
    run(home, "panel", panel)
    write(panel, "[panel]\nlaunchers=loop-staff-tools x-www-browser pcmanfm\nicon_size=36\n")
    run(home, "panel", panel)
    # setup_branding.sh: two whole files, one new
    run(home, "snapshot", gtk, themerc)
    write(gtk, "/* LOOP display branding */\n")
    write(themerc, "# LOOP display branding\n")
    run(home, "wrote", gtk, themerc)
    # the taskbar colors in a user copy of the Pi theme (a folder LOOP made)
    run(home, "snapshot", theme)
    write(theme, '@import url("/usr/share/themes/PiXtrix/gtk-3.0/gtk.css");\n/* LOOP display branding */\n')
    run(home, "wrote", theme)
    # setup_chromium.py
    sys.path.insert(0, os.path.join(ROOT, "src"))
    env_home = os.environ.get("HOME")
    code = (f"import sys; sys.path.insert(0, {os.path.join(ROOT, 'src')!r}); import loop_undo as u; "
            f"u.chromium_snapshot({prefs!r}, {bms!r}, {c('.config/chromium/First Run')!r}); "
            f"u.chromium_wrote('/mnt/loopdata/videos', 'https://library.example', 'Videos')")
    subprocess.run([sys.executable, "-c", code], env=dict(os.environ, HOME=home,
                   XDG_STATE_HOME=os.path.join(home, ".local", "state")), check=True)
    write(prefs, json.dumps({"download": {"default_directory": "/mnt/loopdata/videos", "prompt_for_download": False},
                             "homepage": "x", "bookmark_bar": {"show_on_all_tabs": True}}))
    write(bms, json.dumps({"roots": {"bookmark_bar": {"children": [{"type": "url", "name": "Videos",
                                                                      "url": "https://library.example"}]}}}))
    write(c(".config/chromium/First Run"), "")
    write(c("Desktop/loop-staff-tools.desktop"), "[Desktop Entry]\n")
    assert env_home == os.environ.get("HOME")
    return home, c


# 1. Nothing changed after setup: everything goes back.
home, c = fresh_setup()
out = run(home, "undo")
vlc = read(c(".config/vlc/vlcrc"))
check("loop=0" in vlc and "extraintf=http" not in vlc and "#http-host=" in vlc and "volume=200" in vlc,
      "VLC: LOOP's keys back to the user's values or VLC's defaults; other keys kept")
check("launchers=x-www-browser lxterminal" in read(c(".config/wf-panel-pi/wf-panel-pi.ini")),
      "taskbar launchers restored")
check(read(c(".config/gtk-3.0/gtk.css")) == "/* the user's own */\n", "changed file restored from the original")
check(not os.path.exists(c(".config/labwc/themerc-override")), "file LOOP created is removed")
check(not os.path.exists(c(".local/share/themes/PiXtrix")) and os.path.isdir(c(".local/share/themes")),
      "theme copy LOOP made is removed with its empty theme folder; the themes folder stays")
prefs = json.load(open(c(".config/chromium/Default/Preferences")))
check(prefs["download"].get("default_directory") == "/home/pi/Downloads" and "prompt_for_download" not in
      prefs["download"] and prefs.get("homepage") == "x", "Chromium download folder restored, other prefs kept")
bar = json.load(open(c(".config/chromium/Default/Bookmarks")))["roots"]["bookmark_bar"]["children"]
check([b["name"] for b in bar] == ["News"], "Chromium bookmark removed and the user's bookmarks back")
check(not os.path.exists(c(".config/chromium/First Run")), "Chromium first-run marker LOOP made is removed")
check(not os.path.exists(c("Desktop/loop-staff-tools.desktop")), "desktop icon removed")
check(not os.path.exists(c(".local/state/loop")), "undo record removed when done")

# 1b. Chromium never opened before LOOP: the files LOOP made go too.
home = tempfile.mkdtemp()
code = (f"import sys; sys.path.insert(0, {os.path.join(ROOT, 'src')!r}); import loop_undo as u; "
        f"u.chromium_snapshot({os.path.join(home, '.config/chromium/Default/Preferences')!r}, "
        f"{os.path.join(home, '.config/chromium/Default/Bookmarks')!r}, {os.path.join(home, '.config/chromium/First Run')!r}); "
        f"u.chromium_wrote('/mnt/loopdata/videos', 'https://library.example', 'Videos')")
subprocess.run([sys.executable, "-c", code], env=dict(os.environ, HOME=home,
               XDG_STATE_HOME=os.path.join(home, ".local", "state")), check=True)
write(os.path.join(home, ".config/chromium/Default/Preferences"), json.dumps(
    {"download": {"default_directory": "/mnt/loopdata/videos", "prompt_for_download": False, "directory_upgrade": True},
     "savefile": {"default_directory": "/mnt/loopdata/videos"}, "bookmark_bar": {"show_on_all_tabs": True},
     "browser": {"has_seen_welcome_page": True}}))
write(os.path.join(home, ".config/chromium/Default/Bookmarks"), json.dumps({"roots": {
    "bookmark_bar": {"children": [{"type": "url", "name": "Videos", "url": "https://library.example"}]},
    "other": {"children": []}, "synced": {"children": []}}}))
write(os.path.join(home, ".config/chromium/First Run"), "")
run(home, "undo")
check(not os.path.exists(os.path.join(home, ".config/chromium")), "Chromium files LOOP created from nothing removed")

# 2. Someone changed things after setup: their changes stay.
home, c = fresh_setup()
write(c(".config/gtk-3.0/gtk.css"), "/* IT's later change */\n")
vlc = read(c(".config/vlc/vlcrc")).replace("loop=1", "loop=0")
write(c(".config/vlc/vlcrc"), vlc)
write(c(".config/wf-panel-pi/wf-panel-pi.ini"), "[panel]\nlaunchers=loop-staff-tools x-www-browser geany\n")
out = run(home, "undo")
check(read(c(".config/gtk-3.0/gtk.css")) == "/* IT's later change */\n" and "left .config/gtk-3.0/gtk.css" in out,
      "file changed after setup is left and reported")
check("launchers=x-www-browser geany" in read(c(".config/wf-panel-pi/wf-panel-pi.ini")),
      "edited taskbar keeps its changes; only Staff Tools removed")
check("extraintf=" not in read(c(".config/vlc/vlcrc")).replace("#extraintf=", ""),
      "VLC keys still holding LOOP's values are put back")

# 3. A setup from before the record existed (--legacy): LOOP's own values and files go.
home = tempfile.mkdtemp()
c = lambda p: os.path.join(home, p)  # noqa: E731
write(c(".config/vlc/vlcrc"), "extraintf=http\nhttp-host=127.0.0.1\nhttp-port=8080\nhttp-password=abc\nloop=1\n")
write(c(".config/wf-panel-pi/wf-panel-pi.ini"), "[panel]\nlaunchers=loop-staff-tools x-www-browser pcmanfm\n")
write(c(".config/gtk-3.0/gtk.css"), "/* LOOP display branding */\n")
write(c(".config/gtk-3.0/gtk.css.bak-loop-20261101-000000"), "/* original */\n")
write(c(".config/labwc/themerc-override"), "window.active.title.bg.color: #000\n")
run(home, "undo", "--legacy")
check(read(c(".config/gtk-3.0/gtk.css")) == "/* original */\n", "legacy: oldest LOOP backup restored")
check(not os.path.exists(c(".config/labwc/themerc-override")), "legacy: LOOP-made file removed")
check("loop-staff-tools" not in read(c(".config/wf-panel-pi/wf-panel-pi.ini")), "legacy: launcher removed")
check("extraintf=http" not in read(c(".config/vlc/vlcrc")), "legacy: VLC control interface turned off")

print("all passed" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
