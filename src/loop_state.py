#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Shared state for a LOOP display Pi: Setup/Production mode, burn-in test, software updates.

Everything lives on the USB data drive (<data mount>/state, /mnt/loopdata by default), which stays writable even when
the OS is in read-only mode, so it survives restarts. Used by the player, the Performance
History recorder and Staff Display Tools. Standard library only.

Files (JSON):
  mode.json         {"mode": "setup" | "production", "changed": ...}   (missing = setup)
  burnin.json       {"settings": {...}, "test": {...}}
  maintenance.json  {"stage": ..., "started": ..., "updated": ..., "resume_without_ro": bool}
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_profile  # noqa: E402

DATA = loop_profile.data_mount()
STATE = os.path.join(DATA, "state")
LOGS = os.path.join(DATA, "logs")
MODE_FILE = os.path.join(STATE, "mode.json")
BURNIN_FILE = os.path.join(STATE, "burnin.json")
MAINT_FILE = os.path.join(STATE, "maintenance.json")
CMDLINE = "/boot/firmware/cmdline.txt"
ROOT_HELPER = loop_profile.ROOT_HELPER

TEST_HOURS = (12, 24, 48, 72, 96)
DEFAULT_SETTINGS = {
    "hours": 24,             # test length
    "max_temp_c": 80.0,      # CPU and GPU must stay strictly below
    "max_mem_pct": 80.0,     # memory in use must stay strictly below
    "max_drop_pct": 0.001,   # dropped / (shown + dropped) must stay strictly below
    "require_uptime": True,  # no reboots, power cycles, video restarts or logging gaps
    "read_only": True,       # run the test in read-only mode (recommended)
}

# Update workflow stages (Production Mode, or Setup Mode with read-only on):
#   ro_off_pending  read-only switched off for next boot; restart to continue
#   ready           running read/write; video held; check for / install updates
#   installing      updates being installed (if the Pi restarts now: "interrupted")
#   interrupted     the Pi restarted mid-install; repair before anything else
#   installed       updates installed; restart pending
#   post_update     after the update restart; choose Check For Updates or Enable Read-Only
#   ro_on_pending   read-only switched on for next boot; restart to finish (then the file goes)
# Each stage records the boot it was set in; settle() moves it on after a restart.
# "origin" is "ro" (started from read-only) or "rw" (Setup Mode already read/write).
MAINT_HOLD_STAGES = {"ready", "installing", "interrupted", "installed", "post_update"}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


# --- system facts
def usb_ok():
    return os.path.ismount(DATA)


def ro_now():
    try:
        out = subprocess.run(["findmnt", "-n", "-o", "FSTYPE", "/"], capture_output=True, text=True).stdout
        return out.strip() == "overlay"
    except OSError:
        return False


def data_kept():
    """False when the USB data drive sits under read-only mode's RAM layer (overlayroot recurse=1, for example after
    switching read-only on with raspi-config directly): then nothing written to it survives a restart."""
    try:
        out = subprocess.run(["findmnt", "-n", "-o", "FSTYPE", DATA], capture_output=True, text=True).stdout
        return out.strip() != "overlay"
    except OSError:
        return True


def ro_next():
    try:
        with open(CMDLINE) as f:
            return "overlayroot=tmpfs" in f.read()
    except OSError:
        return False


def ssh_enabled():
    r = subprocess.run(["systemctl", "is-enabled", "ssh"], capture_output=True, text=True)
    return r.stdout.strip() == "enabled"


def boot_id():
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()
    except OSError:
        return ""


def helper_installed():
    return os.path.isfile(ROOT_HELPER) and os.access(ROOT_HELPER, os.X_OK)


# --- mode
def mode():
    return read_json(MODE_FILE, {}).get("mode", "setup")


def set_mode(m):
    write_json(MODE_FILE, {"mode": m, "changed": now_iso()})


# --- burn-in
def burnin():
    d = read_json(BURNIN_FILE, {})
    s = dict(DEFAULT_SETTINGS)
    s.update(d.get("settings", {}))
    return {"settings": s, "test": d.get("test", {"state": "idle"})}


def save_burnin(settings=None, test=None):
    d = burnin()
    if settings is not None:
        d["settings"] = settings
    if test is not None:
        d["test"] = test
    write_json(BURNIN_FILE, d)


def start_test_now(settings):
    start = datetime.now().replace(microsecond=0)
    test = {"state": "running", "started": start.isoformat(),
            "ends": (start + timedelta(hours=settings["hours"])).isoformat(),
            "settings": dict(settings)}
    save_burnin(settings=settings, test=test)
    return test


def mark_test_pending(settings):
    """Read-only test: starts automatically at the next boot (once read-only is active)."""
    save_burnin(settings=settings, test={"state": "pending_restart", "requested": now_iso(),
                                         "settings": dict(settings)})


def promote_pending_test():
    """Called at boot by the recorder: a pending test starts once the requested mode is live."""
    b = burnin()
    t = b["test"]
    if t.get("state") != "pending_restart":
        return None
    want_ro = t.get("settings", b["settings"]).get("read_only", True)
    if want_ro != ro_now():
        t = dict(t, state="aborted", stopped=now_iso(),
                 reason=f"Read-only mode was {'off' if want_ro else 'still on'} after the restart.")
        save_burnin(test=t)
        return t
    return start_test_now(t.get("settings", b["settings"]))


def stop_test(reason="Stopped"):
    b = burnin()
    t = dict(b["test"])
    if t.get("state") in ("running", "pending_restart"):
        t.update(state="stopped", stopped=now_iso(), reason=reason)
        save_burnin(test=t)
    return t


def retention_hours():
    """How much Performance History to keep: 24 h in production; during setup, at least
    7 days and at least the burn-in test length plus a day."""
    if mode() == "production":
        return 24.0
    hours = burnin()["settings"].get("hours", 24)
    return float(max(168, hours + 24))


# --- software update workflow
def maint():
    return settle()


def settle():
    """Advance the update workflow after a restart. Safe to call often, from any process."""
    d = read_json(MAINT_FILE, {})
    stage = d.get("stage")
    if not stage or d.get("boot") == boot_id():
        return d
    nxt, note = stage, None
    if stage == "ro_off_pending":
        nxt, note = ("ready", None) if not ro_now() else ("ro_off_pending", "Read-only mode was still on after the restart.")
    elif stage == "installing":
        nxt = "interrupted"
    elif stage == "installed":
        nxt = "post_update"
    elif stage == "ro_on_pending":
        if ro_now():
            remove(MAINT_FILE)
            return {}
        nxt, note = "post_update", "Read-only mode did not turn on after the restart. Try again."
    d.update(stage=nxt, boot=boot_id(), updated_at=now_iso(), note=note)
    try:
        write_json(MAINT_FILE, d)
    except OSError:
        pass
    return d


def maint_stage():
    return maint().get("stage")


def set_maint(stage, **extra):
    d = read_json(MAINT_FILE, {})
    # Any step change pauses the video again unless resume_without_ro is passed explicitly.
    d.update(extra, stage=stage, updated_at=now_iso(), boot=boot_id(), note=extra.get("note"),
             resume_without_ro=bool(extra.get("resume_without_ro", False)))
    d.setdefault("started", now_iso())
    write_json(MAINT_FILE, d)


def end_maint():
    remove(MAINT_FILE)


def video_held():
    """True when the player must not resume video (updates in progress, read/write)."""
    d = maint()
    return d.get("stage") in MAINT_HOLD_STAGES and not d.get("resume_without_ro")
