#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Performance History logger for LOOP display Pis (Pi 4 + VLC 3.x).

Every INTERVAL seconds, appends one CSV row to ~/burnin/logs/burnin-YYYY-MM-DD.csv with:
  - SoC temperatures (CPU via thermal_zone0, GPU via `vcgencmd measure_temp`)
  - throttle flags, ARM clock, load average
  - system memory + CMA (GPU/video buffer) memory, VLC process memory
  - VLC frame statistics from VLC's local HTTP interface (127.0.0.1 only)

VLC resets its frame counters every time the media restarts (each loop), so this script
accumulates deltas and treats a counter that goes down as a reset. Drops in the last
<INTERVAL seconds before a reset are not seen, so totals can be slightly low.

Black box: a daily file is deleted once its newest entry is older than the retention window
(loop_state.retention_hours(): 24 h in Production, 7+ days in Setup; else KEEP_HOURS),
so at least that much history is always on hand and storage stays small (~2.5 MB a day). Shown to
staff as "Performance History" in Staff Display Tools.

Standard library only. The VLC HTTP password is read from ~/.config/vlc/vlcrc.
"""
import base64
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), os.path.expanduser("~/loop")]
try:
    import loop_state
except ImportError:  # older install without the shared state module
    loop_state = None

INTERVAL = float(os.environ.get("BURNIN_INTERVAL", "5"))
LOG_DIR = os.path.expanduser(os.environ.get("BURNIN_LOG_DIR") or (
    os.path.join(loop_state.DATA, "logs") if loop_state else "~/burnin/logs"))
VLCRC = os.path.expanduser("~/.config/vlc/vlcrc")
KEEP_HOURS = float(os.environ.get("BURNIN_KEEP_HOURS", "24"))


def keep_hours():
    """Retention follows the mode: 24 h in Production, and in Setup at least 7 days and the
    burn-in test length plus a day (loop_state). BURNIN_KEEP_HOURS is the fallback."""
    try:
        if loop_state and loop_state.usb_ok():
            return loop_state.retention_hours()
    except Exception:
        pass
    return KEEP_HOURS


def prune_old_logs():
    """Delete a daily file only once its newest entry is older than KEEP_HOURS.

    Files are per day, so this always leaves at least KEEP_HOURS of history
    (at most one extra day on disk). Today's file is never deleted.
    """
    cutoff = time.time() - keep_hours() * 3600
    today = f"burnin-{datetime.now():%Y-%m-%d}.csv"
    for f in os.listdir(LOG_DIR):
        if not re.fullmatch(r"burnin-\d{4}-\d{2}-\d{2}\.csv", f) or f == today:
            continue
        path = os.path.join(LOG_DIR, f)
        try:
            if os.path.getmtime(path) < cutoff:  # last write = newest entry
                os.remove(path)
                print(f"pruned old log {f}", flush=True)
        except OSError:
            pass

FIELDS = [
    "timestamp", "uptime_s",
    "cpu_temp_c", "gpu_temp_c", "throttled", "arm_mhz", "load1",
    "mem_total_mb", "mem_avail_mb", "mem_used_pct", "swap_used_mb", "cma_free_mb",
    "vlc_pid", "vlc_rss_mb", "vlc_restart",
    "vlc_ok", "vlc_state", "vlc_time_s", "vlc_length_s", "fps",
    "displayed_delta", "lost_delta", "decoded_delta", "counter_reset",
    "displayed_total", "lost_total", "decoded_total",
    "interval_s",
]


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def vcgencmd(*args):
    try:
        return subprocess.run(["vcgencmd", *args], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def cpu_temp():
    raw = read("/sys/class/thermal/thermal_zone0/temp")
    return round(int(raw) / 1000, 1) if raw else ""


def gpu_temp():
    m = re.search(r"temp=([\d.]+)", vcgencmd("measure_temp"))
    return float(m.group(1)) if m else ""


def throttled():
    m = re.search(r"throttled=(0x[0-9a-fA-F]+)", vcgencmd("get_throttled"))
    return m.group(1) if m else ""


def arm_mhz():
    m = re.search(r"=(\d+)", vcgencmd("measure_clock", "arm"))
    return round(int(m.group(1)) / 1e6) if m else ""


def meminfo():
    info = {}
    for line in (read("/proc/meminfo") or "").splitlines():
        k, _, v = line.partition(":")
        info[k] = int(v.split()[0]) if v.split() else 0
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", 0)
    return {
        "mem_total_mb": round(total / 1024),
        "mem_avail_mb": round(avail / 1024),
        "mem_used_pct": round(100 * (total - avail) / total, 1) if total else "",
        "swap_used_mb": round((info.get("SwapTotal", 0) - info.get("SwapFree", 0)) / 1024),
        "cma_free_mb": round(info.get("CmaFree", 0) / 1024) if "CmaFree" in info else "",
    }


def vlc_proc():
    """Return (pid, rss_mb) of the oldest running vlc process, or ("", "")."""
    best = None
    for pid in filter(str.isdigit, os.listdir("/proc")):
        comm = (read(f"/proc/{pid}/comm") or "").strip()
        if comm != "vlc":
            continue
        start = int((read(f"/proc/{pid}/stat") or "0 " * 22).rsplit(")", 1)[-1].split()[19])
        if best is None or start < best[1]:
            best = (pid, start)
    if not best:
        return "", ""
    m = re.search(r"VmRSS:\s+(\d+)", read(f"/proc/{best[0]}/status") or "")
    return int(best[0]), (round(int(m.group(1)) / 1024, 1) if m else "")


def vlc_config():
    host, port, pw = "127.0.0.1", "8080", ""
    for line in (read(VLCRC) or "").splitlines():
        if line.startswith("http-password="):
            pw = line.split("=", 1)[1].strip()
        elif line.startswith("http-port="):
            port = line.split("=", 1)[1].strip() or port
    return host, port, pw


def vlc_status():
    host, port, pw = vlc_config()
    req = urllib.request.Request(f"http://{host}:{port}/requests/status.json")
    req.add_header("Authorization", "Basic " + base64.b64encode(f":{pw}".encode()).decode())
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.load(r)


def stream_fps(status):
    cats = (status.get("information") or {}).get("category") or {}
    for cat in cats.values():
        if isinstance(cat, dict) and cat.get("Type") == "Video":
            for key in ("Frame_rate", "Frame rate"):
                if key in cat:
                    try:
                        return round(float(cat[key]), 3)
                    except ValueError:
                        pass
    return ""


def log_path():
    return os.path.join(LOG_DIR, f"burnin-{datetime.now():%Y-%m-%d}.csv")


def write_row(row):
    path = log_path()
    new = not os.path.exists(path)
    if new:
        prune_old_logs()  # a new day started: drop files beyond the black-box window
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def wait_for_data_drive():
    """When the logs live on the data drive, wait for it to be mounted (a USB drive can appear late at boot)
    instead of failing; writing into the empty mount folder would also be refused."""
    if not loop_state or not LOG_DIR.startswith(loop_state.DATA.rstrip("/") + "/"):
        return
    waited = 0
    while not os.path.ismount(loop_state.DATA):
        if waited % 60 == 0:
            print(f"burnin_logger: waiting for the data drive at {loop_state.DATA}", flush=True)
        time.sleep(5)
        waited += 5


def main():
    wait_for_data_drive()
    os.makedirs(LOG_DIR, exist_ok=True)
    prev = {"displayedpictures": None, "lostpictures": None, "decodedvideo": None}
    totals = {"displayedpictures": 0, "lostpictures": 0, "decodedvideo": 0}
    last_pid = None
    last_t = time.monotonic()
    ticks = 0
    print(f"burnin_logger: interval={INTERVAL}s logdir={LOG_DIR} keep_hours={keep_hours():g}", flush=True)
    prune_old_logs()
    # A burn-in test requested before a restart starts now, once its mode is confirmed live.
    try:
        if loop_state:
            loop_state.settle()  # move a software update on to its next step after a restart
            t = loop_state.promote_pending_test()
            if t:
                print(f"burn-in test: {t.get('state')} {t.get('started', '')} {t.get('reason', '')}".strip(), flush=True)
    except Exception as e:
        print(f"burn-in test start failed: {e}", file=sys.stderr, flush=True)

    while True:
        loop_start = time.monotonic()
        dt = loop_start - last_t
        last_t = loop_start

        row = dict.fromkeys(FIELDS, "")
        row["timestamp"] = datetime.now().isoformat(timespec="seconds")
        row["uptime_s"] = int(float((read("/proc/uptime") or "0").split()[0]))
        row["cpu_temp_c"] = cpu_temp()
        row["gpu_temp_c"] = gpu_temp()
        row["throttled"] = throttled()
        row["arm_mhz"] = arm_mhz()
        row["load1"] = (read("/proc/loadavg") or "").split(" ")[0]
        row.update(meminfo())
        row["interval_s"] = round(dt, 2)

        pid, rss = vlc_proc()
        row["vlc_pid"], row["vlc_rss_mb"] = pid, rss
        restarted = pid != "" and last_pid is not None and pid != last_pid
        row["vlc_restart"] = int(restarted)
        if restarted or pid == "":
            prev = dict.fromkeys(prev)  # new process: counters start over
        last_pid = pid or last_pid

        try:
            st = vlc_status()
            stats = st.get("stats") or {}
            row["vlc_ok"] = 1
            row["vlc_state"] = st.get("state", "")
            row["vlc_time_s"] = st.get("time", "")
            row["vlc_length_s"] = st.get("length", "")
            row["fps"] = stream_fps(st)
            reset = 0
            for key, col in (("displayedpictures", "displayed_delta"),
                             ("lostpictures", "lost_delta"),
                             ("decodedvideo", "decoded_delta")):
                cur = int(stats.get(key, 0) or 0)
                p = prev[key]
                if p is None:
                    delta = 0  # first sample after start/restart: establish baseline
                elif cur < p:
                    delta = cur  # media restarted (loop): counters reset to 0
                    reset = 1
                else:
                    delta = cur - p
                prev[key] = cur
                totals[key] += delta
                row[col] = delta
            row["counter_reset"] = reset
        except Exception as e:  # VLC not running or HTTP interface not enabled
            row["vlc_ok"] = 0
            row["vlc_state"] = type(e).__name__
            prev = dict.fromkeys(prev)

        row["displayed_total"] = totals["displayedpictures"]
        row["lost_total"] = totals["lostpictures"]
        row["decoded_total"] = totals["decodedvideo"]

        try:
            write_row(row)
        except OSError as e:
            print(f"write failed: {e}", file=sys.stderr, flush=True)

        ticks += 1
        if loop_state and ticks % 12 == 0:  # about once a minute: start a test waiting on a restart
            try:                           # (in case the USB drive mounted after this started)
                loop_state.promote_pending_test()
                loop_state.settle()
            except Exception:
                pass

        time.sleep(max(0.0, INTERVAL - (time.monotonic() - loop_start)))


if __name__ == "__main__":
    main()
