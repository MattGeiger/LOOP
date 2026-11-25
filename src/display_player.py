#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""LOOP display player v2: the newest video in the drop folder plays, on a loop.

Run by the user systemd service loop-player.service (starts at boot, restarts on exit).

What plays, in order of preference:
  1. The newest *finished* video in the drop folder (USB drive, <data mount>/videos).
     Half-finished downloads (.crdownload, .part, ...) are ignored, and a file must keep the
     same size for two checks and pass a quick ffprobe before it is used.
  2. The backup video on the SD card (if the USB drive or its videos are missing).
  3. The branded idle image (if nothing else can play).

Switching: a new video is queued behind the current one, so it starts when the current loop
finishes; nothing is cut off mid-ad. Switches away from a missing file or from the idle image
happen at once. VLC is never restarted to switch, so the screen doesn't flash.

Software updates: while Staff Display Tools has the Pi in Read/write Mode for updates
(loop_state.video_held()), the branded idle screen shows instead of video and Staff Display
Tools is opened on its Update Software view, so the screen never runs ads unprotected.

Clean-up: only the newest KEEP videos in the drop folder are kept.
Status for staff tools: <state_dir>/status.json. Events: <log_dir>/player.log.
Settings: profile.json and site.json (loop_profile); an optional ~/loop/config.json overrides them. Standard library only.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import loop_state
except ImportError:  # older install without the shared state module
    loop_state = None

HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(HOME, "loop", "config.json")
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import loop_profile
    _DATA = loop_profile.data_mount()
except ImportError:
    loop_profile = None
    _DATA = "/mnt/loopdata"
DEFAULTS = {
    "videos_dir": os.path.join(_DATA, "videos"),
    "state_dir": os.path.join(_DATA, "state"),
    "log_dir": os.path.join(_DATA, "logs"),
    "backup_video": loop_profile.backup_video() if loop_profile else os.path.join(HOME, "loop", "backup.mp4"),
    "idle_image": loop_profile.idle_media() if loop_profile else os.path.join(HOME, "loop", "idle.png"),
    "keep": 3,
}
VIDEO_EXT = (".mp4", ".m4v", ".mov", ".mkv")
VLCRC = os.path.join(HOME, ".config", "vlc", "vlcrc")
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
POLL = 5          # seconds between checks
MIN_AGE = 10      # a file must be unmodified this long before it is considered finished


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    for k in ("backup_video", "idle_image", "videos_dir", "state_dir", "log_dir"):
        cfg[k] = os.path.expanduser(cfg[k])
    # Prefer the idle screen as an H.264 MP4 (hardware decoded, ~8% CPU) over the PNG
    # (VLC software path). The PNG stays as the fallback if the MP4 is missing.
    idle_video = os.path.splitext(cfg["idle_image"])[0] + ".mp4"
    if cfg["idle_image"].endswith(".png") and os.path.isfile(idle_video):
        cfg["idle_image"] = idle_video
    return cfg


CFG = load_config()


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    try:
        os.makedirs(CFG["log_dir"], exist_ok=True)
        path = os.path.join(CFG["log_dir"], "player.log")
        # Keep the event log bounded: past 512 KB, keep only the newest half.
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            with open(path) as f:
                lines = f.readlines()
            with open(path, "w") as f:
                f.writelines(lines[len(lines) // 2:])
        with open(path, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- choosing media
class DropFolder:
    """Tracks files in the drop folder and decides which are finished and playable."""

    def __init__(self, path):
        self.path = path
        self.seen = {}      # path -> (size, mtime) at last check
        self.ready = {}     # path -> mtime, files confirmed finished + playable
        self.bad = {}       # path -> (size, mtime) that failed ffprobe

    def scan(self):
        now = time.time()
        try:
            names = os.listdir(self.path)
        except OSError:
            self.seen, self.ready = {}, {}
            return []
        current = {}
        for n in names:
            p = os.path.join(self.path, n)
            if n.startswith(".") or not n.lower().endswith(VIDEO_EXT):
                continue  # includes .crdownload / .part partial downloads
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_size <= 0:
                continue
            sig = (st.st_size, st.st_mtime)
            current[p] = sig
            if p in self.ready and self.ready[p] == st.st_mtime:
                continue
            self.ready.pop(p, None)
            stable = self.seen.get(p) == sig and now - st.st_mtime >= MIN_AGE
            if stable and self.bad.get(p) != sig:
                if probe_ok(p):
                    self.ready[p] = st.st_mtime
                    log(f"ready: {n}")
                else:
                    self.bad[p] = sig
                    log(f"skipped (not a playable video): {n}")
        self.seen = current
        for p in list(self.ready):
            if p not in current:
                self.ready.pop(p)
        return sorted(self.ready, key=lambda p: self.ready[p], reverse=True)

    def newest(self):
        files = self.scan()
        return files[0] if files else None

    def cleanup(self, protect):
        files = sorted(self.ready, key=lambda p: self.ready[p], reverse=True)
        for p in files[CFG["keep"]:]:
            if p in protect:
                continue
            try:
                os.remove(p)
                self.ready.pop(p, None)
                log(f"cleaned up old video: {os.path.basename(p)}")
            except OSError as e:
                log(f"clean-up failed for {os.path.basename(p)}: {e}")


def probe_ok(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
        return r.returncode == 0 and "video" in r.stdout
    except Exception:
        return True  # if ffprobe itself is unavailable, don't block playback


def fallback_media():
    if os.path.isfile(CFG["backup_video"]):
        return CFG["backup_video"], "backup"
    return CFG["idle_image"], "idle"


# ---------------------------------------------------------------- VLC control
def http_password():
    try:
        with open(VLCRC) as f:
            for line in f:
                if line.startswith("http-password="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


PW = http_password()


def vlc(path, **params):
    url = f"http://127.0.0.1:8080/requests/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Basic " + base64.b64encode(f":{PW}".encode()).decode())
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.load(r)


def uri(path):
    return "file://" + urllib.parse.quote(path)


def uri_path(u):
    return urllib.parse.unquote(urllib.parse.urlparse(u).path) if u.startswith("file://") else u


def playlist():
    """[(id, path, is_current)] for the items in VLC's playlist."""
    items = []

    def walk(node):
        if node.get("type") == "leaf" and node.get("uri"):
            items.append((node["id"], uri_path(node["uri"]), node.get("current") == "current"))
        for c in node.get("children", []) or []:
            walk(c)

    tree = vlc("playlist.json")
    for top in tree.get("children", []):
        if top.get("name") in ("Playlist", "Liste de lecture") or top.get("id") == "1":
            walk(top)
    return items


def play_now(path):
    """Replace the playlist with path and start it immediately."""
    vlc("status.json", command="in_play", input=uri(path))
    time.sleep(1)
    for item_id, p, _ in playlist():
        if p != path:
            vlc("status.json", command="pl_delete", id=item_id)


def queue_next(path):
    vlc("status.json", command="in_enqueue", input=uri(path))


def wait_for_desktop(timeout=600):
    sock = os.path.join(RUNTIME, "wayland-0")
    start = time.monotonic()
    while not os.path.exists(sock):
        if time.monotonic() - start > timeout:
            log("desktop not found; exiting so systemd retries")
            sys.exit(1)
        time.sleep(2)
    time.sleep(5)


def wait_for_drive(timeout=30):
    mnt = os.path.dirname(CFG["videos_dir"].rstrip("/"))
    start = time.monotonic()
    while not os.path.ismount(mnt) and time.monotonic() - start < timeout:
        time.sleep(1)
    return os.path.ismount(mnt)


def staff_tools_open():
    """True while Staff Display Tools (or its Help, About or admin windows) is open. It closes itself after
    10 minutes without use, so a pause for it can never leave the screen stopped for long."""
    try:
        with open(os.path.join(RUNTIME, "loop-staff-tools.pid")) as f:
            os.kill(int(f.read().strip()), 0)
            return True
    except (OSError, ValueError):
        return False


def staff_busy():
    """True while Staff Tools or Chromium is open, so fullscreen isn't forced back on them."""
    return staff_tools_open() or subprocess.run(["pgrep", "-x", "chromium"], capture_output=True).returncode == 0


def burnin_running():
    try:
        return bool(loop_state) and loop_state.burnin().get("state") == "running"
    except Exception:
        return False


def video_held():
    try:
        return bool(loop_state and loop_state.video_held())
    except Exception:
        return False


def open_update_view(env):
    """Bring up Staff Display Tools on its Update Software view (it ignores a second copy)."""
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "staff_tools.py")
    try:
        subprocess.Popen(["/usr/bin/python3", tool, "--update"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        log("software update in progress: opened Staff Display Tools")
    except OSError as e:
        log(f"could not open Staff Display Tools: {e}")


def write_status(status):
    try:
        os.makedirs(CFG["state_dir"], exist_ok=True)
        tmp = os.path.join(CFG["state_dir"], "status.json.tmp")
        with open(tmp, "w") as f:
            json.dump(status, f, indent=2)
        os.replace(tmp, os.path.join(CFG["state_dir"], "status.json"))
    except OSError:
        pass


# ---------------------------------------------------------------- main loop
WIZARD_LOCK = os.path.join(RUNTIME, "loop-setup-wizard.pid")
CLOSED_WAIT_S = 60  # after someone closes VLC on purpose, give them a minute on the desktop before it returns


def wizard_open():
    try:
        with open(WIZARD_LOCK) as f:
            os.kill(int(f.read().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def main():
    wait_for_desktop()
    if wizard_open() or staff_tools_open():
        log("waiting: LOOP Setup or Staff Display Tools is open (the video starts when it closes)")
        while wizard_open() or staff_tools_open():
            time.sleep(2)
    drive_ok = wait_for_drive()
    log(f"starting; USB drive {'mounted' if drive_ok else 'NOT mounted'}")
    folder = DropFolder(CFG["videos_dir"])

    # First pass: a file already sitting in the folder counts as finished (it was there
    # before this boot), so the display doesn't wait out two checks at startup.
    folder.scan()
    for p, sig in folder.seen.items():
        if probe_ok(p):
            folder.ready[p] = sig[1]
    start = folder.newest() if folder.ready else None
    media, source = (start, "usb") if start else fallback_media()
    if video_held():
        media, source = CFG["idle_image"], "idle (software update)"
    log(f"playing {os.path.basename(media)} ({source})")

    env = dict(os.environ, WAYLAND_DISPLAY="wayland-0", DISPLAY=":0", XDG_RUNTIME_DIR=RUNTIME)
    proc = subprocess.Popen([
        "/usr/bin/vlc", "--fullscreen", "--loop", "--no-video-title-show",
        "--qt-continue=0", "--no-qt-privacy-ask", "--image-duration=-1",
        "--image-fps=1",  # the still idle image is redrawn once a second, not 10x (cuts CPU/heat)
        "--extraintf=http", "--http-host=127.0.0.1", "--http-port=8080",
        media,
    ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    since = datetime.now().isoformat(timespec="seconds")
    started_at = time.monotonic()
    idle_flag = os.path.join(CFG["state_dir"], "idle-override")
    not_fullscreen_since = None
    last_update_open = None
    paused_for_staff = False

    while proc.poll() is None:
        time.sleep(POLL)
        newest = folder.newest()
        staff_idle = os.path.exists(idle_flag)
        held = video_held()
        if held:
            desired, dsource = CFG["idle_image"], "idle (software update)"
            # Keep the update steps on screen: reopen Staff Display Tools if it was closed,
            # at most every 10 minutes (the first time ~20 s after the desktop is up).
            if not staff_busy() and (last_update_open is None or time.monotonic() - last_update_open > 600):
                if last_update_open is not None or time.monotonic() - started_at > 20:
                    open_update_view(env)
                    last_update_open = time.monotonic()
        elif staff_idle:
            desired, dsource = CFG["idle_image"], "idle (staff switch)"
        else:
            desired, dsource = (newest, "usb") if newest else fallback_media()
        try:
            items = playlist()
        except Exception:
            continue  # VLC still starting or briefly busy
        current = next((p for _, p, cur in items if cur), None)
        paths = [p for _, p, _ in items]

        # While Staff Display Tools is open the video pauses and leaves fullscreen, so it never covers the
        # window or Help; it resumes, fullscreen, when the window closes. During a burn-in test it keeps playing
        # (in a window), since the test checks the video never stops.
        try:
            if staff_tools_open() and not burnin_running() and not paused_for_staff:
                st = vlc("status.json")
                if st.get("state") == "playing":
                    vlc("status.json", command="pl_forcepause")
                if st.get("fullscreen") not in (False, 0, "false"):
                    vlc("status.json", command="fullscreen")
                paused_for_staff = True
                log("paused while Staff Display Tools is open")
            elif paused_for_staff and (not staff_tools_open() or burnin_running()):
                vlc("status.json", command="pl_forceresume")
                if vlc("status.json").get("fullscreen") in (False, 0, "false"):
                    vlc("status.json", command="fullscreen")
                paused_for_staff = False
                log("resumed")
        except Exception:
            pass

        # If someone leaves fullscreen (double-click, Esc), go back after 2 minutes, but not
        # while staff are working (Staff Tools or the browser open).
        try:
            fs = vlc("status.json").get("fullscreen")
            if fs in (False, 0, "false") and (staff_busy() or held):
                not_fullscreen_since = None
            elif fs in (False, 0, "false"):
                not_fullscreen_since = not_fullscreen_since or time.monotonic()
                if time.monotonic() - not_fullscreen_since > 120:
                    vlc("status.json", command="fullscreen")
                    log("returned VLC to fullscreen")
                    not_fullscreen_since = None
            else:
                not_fullscreen_since = None
        except Exception:
            pass

        try:
            if current != desired:
                current_gone = current is None or not os.path.exists(current)
                if current_gone or current == CFG["idle_image"] or desired == CFG["idle_image"]:
                    play_now(desired)
                    log(f"switched now to {os.path.basename(desired)} ({dsource})")
                    since = datetime.now().isoformat(timespec="seconds")
                elif desired not in paths:
                    for item_id, p, cur in items:
                        if not cur:
                            vlc("status.json", command="pl_delete", id=item_id)  # drop a stale queued item
                    queue_next(desired)
                    log(f"queued {os.path.basename(desired)} ({dsource}); starts after the current loop")
            elif len(items) > 1:
                for item_id, p, cur in items:
                    if not cur:
                        vlc("status.json", command="pl_delete", id=item_id)
                log(f"now playing {os.path.basename(desired)} ({dsource}); previous video removed from playlist")
                since = datetime.now().isoformat(timespec="seconds")
        except Exception as e:
            log(f"VLC command failed: {e}")

        folder.cleanup(protect={current, desired})
        write_status({
            "updated": datetime.now().isoformat(timespec="seconds"),
            "playing": os.path.basename(current) if current else None,
            "source": "usb" if current and current.startswith(CFG["videos_dir"]) else
                      ("idle" if current == CFG["idle_image"] else "backup" if current else None),
            "playing_since": since,
            "queued": os.path.basename(desired) if current != desired else None,
            "usb_mounted": os.path.ismount(os.path.dirname(CFG["videos_dir"].rstrip("/"))),
            "idle_override": staff_idle,
            "update_hold": held,
            "paused_for_staff": paused_for_staff,
            "videos_in_folder": [os.path.basename(p) for p in
                                 sorted(folder.ready, key=lambda p: folder.ready[p], reverse=True)],
        })

    log(f"VLC exited with code {proc.returncode}")
    if proc.returncode == 0:  # closed on purpose (its window or Quit), not a crash
        log(f"VLC was closed; the video comes back in {CLOSED_WAIT_S} seconds")
        time.sleep(CLOSED_WAIT_S)
    sys.exit(0)


if __name__ == "__main__":
    main()
