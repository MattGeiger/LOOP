#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Summarize burn-in CSVs written by burnin_logger.py.

Usage:
  python3 burnin_summary.py                 # all files in ~/burnin/logs
  python3 burnin_summary.py --hours 24      # only the last 24 hours
  python3 burnin_summary.py --csv out.csv   # also write the hourly table as CSV
  python3 burnin_summary.py path/to/*.csv   # specific files (e.g. copied to a Mac)

Per hour: frames shown, frames dropped (VLC "lost pictures"), drops/hour, effective fps
vs. the video's fps, CPU/GPU temperature min/avg/max, lowest available memory, VLC memory,
throttle flags, VLC restarts, and samples where VLC's stats were unreachable.
"""
import argparse
import csv
import glob
import os
from collections import OrderedDict
from datetime import datetime, timedelta

THROTTLE_BITS = {
    0: "under-voltage now", 1: "freq capped now", 2: "throttled now", 3: "soft temp limit now",
    16: "under-voltage occurred", 17: "freq cap occurred", 18: "throttling occurred",
    19: "soft temp limit occurred",
}



def _usb_logs():
    try:
        sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), os.path.expanduser("~/loop")]
        import loop_profile
        return os.path.join(loop_profile.data_mount(), "logs")
    except ImportError:
        return "/mnt/loopdata/logs"

def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load(paths):
    rows = []
    for p in sorted(paths):
        with open(p, newline="") as fh:
            rows.extend(csv.DictReader(fh))
    for r in rows:
        r["_ts"] = datetime.fromisoformat(r["timestamp"])
    rows.sort(key=lambda r: r["_ts"])
    return rows


def new_bucket():
    return {"n": 0, "shown": 0, "lost": 0, "decoded": 0, "play_s": 0.0, "fps": None,
            "cpu": [], "gpu": [], "avail": [], "rss": [], "throttle": 0,
            "restarts": 0, "vlc_down": 0, "resets": 0}


def add(b, r):
    b["n"] += 1
    b["shown"] += int(f(r["displayed_delta"]) or 0)
    b["lost"] += int(f(r["lost_delta"]) or 0)
    b["decoded"] += int(f(r["decoded_delta"]) or 0)
    if r["vlc_state"] == "playing":
        b["play_s"] += f(r["interval_s"]) or 0
    if f(r["fps"]):
        b["fps"] = f(r["fps"])
    for key, col in (("cpu", "cpu_temp_c"), ("gpu", "gpu_temp_c"),
                     ("avail", "mem_avail_mb"), ("rss", "vlc_rss_mb")):
        v = f(r[col])
        if v is not None:
            b[key].append(v)
    try:
        b["throttle"] |= int(r["throttled"], 16)
    except (TypeError, ValueError):
        pass
    b["restarts"] += int(f(r["vlc_restart"]) or 0)
    b["resets"] += int(f(r["counter_reset"]) or 0)
    if r["vlc_ok"] != "1":
        b["vlc_down"] += 1


def stats(vals):
    if not vals:
        return ("", "", "")
    return (round(min(vals), 1), round(sum(vals) / len(vals), 1), round(max(vals), 1))


def flags(mask):
    return ", ".join(name for bit, name in THROTTLE_BITS.items() if mask & (1 << bit)) or "none"


def row_for(label, b):
    hrs = b["n"] and (b["play_s"] / 3600)
    eff = round(b["shown"] / b["play_s"], 2) if b["play_s"] else ""
    cpu, gpu = stats(b["cpu"]), stats(b["gpu"])
    return OrderedDict([
        ("period", label), ("samples", b["n"]),
        ("frames_shown", b["shown"]), ("frames_dropped", b["lost"]),
        ("drops_per_hour", round(b["lost"] / hrs, 1) if hrs else ""),
        ("drop_pct", round(100 * b["lost"] / (b["shown"] + b["lost"]), 3) if (b["shown"] + b["lost"]) else ""),
        ("video_fps", b["fps"] or ""), ("effective_fps", eff),
        ("cpu_min", cpu[0]), ("cpu_avg", cpu[1]), ("cpu_max", cpu[2]),
        ("gpu_min", gpu[0]), ("gpu_avg", gpu[1]), ("gpu_max", gpu[2]),
        ("mem_avail_min_mb", min(b["avail"]) if b["avail"] else ""),
        ("vlc_rss_min_mb", min(b["rss"]) if b["rss"] else ""),
        ("vlc_rss_max_mb", max(b["rss"]) if b["rss"] else ""),
        ("throttle_hex", hex(b["throttle"])), ("vlc_restarts", b["restarts"]),
        ("loops", b["resets"]), ("vlc_unreachable", b["vlc_down"]),
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--hours", type=float)
    ap.add_argument("--csv")
    a = ap.parse_args()

    log_dir = os.environ.get("BURNIN_LOG_DIR") or (
        _usb_logs() if os.path.isdir(_usb_logs()) else os.path.expanduser("~/burnin/logs"))
    paths = a.files or glob.glob(os.path.join(log_dir, "burnin-*.csv"))
    rows = load(paths)
    if a.hours:
        cutoff = datetime.now() - timedelta(hours=a.hours)
        rows = [r for r in rows if r["_ts"] >= cutoff]
    if not rows:
        print("No data.")
        return

    hourly, total = OrderedDict(), new_bucket()
    for r in rows:
        key = r["_ts"].strftime("%Y-%m-%d %H:00")
        add(hourly.setdefault(key, new_bucket()), r)
        add(total, r)

    table = [row_for(k, b) for k, b in hourly.items()]
    cols = ["period", "frames_dropped", "drops_per_hour", "effective_fps",
            "cpu_min", "cpu_max", "gpu_min", "gpu_max", "mem_avail_min_mb",
            "vlc_rss_max_mb", "throttle_hex", "vlc_restarts", "vlc_unreachable"]
    widths = {c: max(len(c), *(len(str(t[c])) for t in table)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for t in table:
        print("  ".join(str(t[c]).ljust(widths[c]) for c in cols))

    tot = row_for("TOTAL", total)
    span = rows[-1]["_ts"] - rows[0]["_ts"]
    print(f"\nHost data span: {rows[0]['_ts']} -> {rows[-1]['_ts']} ({span})")
    print(f"Frames shown {tot['frames_shown']:,}  dropped {tot['frames_dropped']:,}  "
          f"({tot['drop_pct']}%)  drops/hour {tot['drops_per_hour']}")
    print(f"Video fps {tot['video_fps']}  effective fps {tot['effective_fps']}  loops {tot['loops']}")
    print(f"CPU temp  min {tot['cpu_min']}  avg {tot['cpu_avg']}  max {tot['cpu_max']} C")
    print(f"GPU temp  min {tot['gpu_min']}  avg {tot['gpu_avg']}  max {tot['gpu_max']} C")
    print(f"Lowest available memory {tot['mem_avail_min_mb']} MB; "
          f"VLC memory {tot['vlc_rss_min_mb']} -> {tot['vlc_rss_max_mb']} MB")
    print(f"Throttle flags seen: {flags(total['throttle'])}")
    print(f"VLC restarts {tot['vlc_restarts']}; samples with VLC stats unreachable {tot['vlc_unreachable']}")

    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
            w.writeheader()
            w.writerows(table + [tot])
        print(f"\nHourly table written to {a.csv}")


if __name__ == "__main__":
    main()
