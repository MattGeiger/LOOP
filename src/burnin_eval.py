#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Burn-in pass/fail judge for a LOOP display Pi.

Reads the Performance History CSVs (burnin_logger.py) for the window of the current burn-in
test (loop_state.burnin()["test"]) and checks it against that test's own settings:

  temperature  CPU and GPU strictly below max_temp_c in every sample
  memory       mem_used_pct strictly below max_mem_pct in every sample
  frames       lost / (displayed + lost) strictly below max_drop_pct, from the raw frame
               counts summed over the whole test (rounded only for display); judged at the end
  uptime       (if require_uptime) no reboot (uptime went down), no video restart, no logging
               gap over GAP_S seconds, and VLC answering and playing (no stop longer than ~15 s)

The first breach of each rule is recorded with its time, and recording continues so the full
picture is available. Verdicts: RUNNING (on track), FAILING (already broken, still recording),
PASS, FAIL, or NO DATA.

Usage:  burnin_eval.py            human-readable report of the current test
        burnin_eval.py --json     the same as JSON
Standard library only.
"""
import csv
import glob
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_state  # noqa: E402

GAP_S = 30           # samples are every 5 s; a longer silence means the recorder or Pi stopped
STALL_SAMPLES = 3    # consecutive not-playing samples (about 15 s) that count as a stop
START_GRACE_S = 120  # the recorder may take this long to write its first row after boot
STARTUP_S = 300      # after the test starts (usually at boot), the video has this long to start playing;
                     # player starts, stops and restarts before the first playing sample are start-up, not failures


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rows(log_dir, start, end):
    """Rows with start <= timestamp <= end, oldest first, from the daily CSVs covering it."""
    out = []
    day = start.date()
    while day <= end.date():
        path = os.path.join(log_dir, f"burnin-{day:%Y-%m-%d}.csv")
        try:
            with open(path, newline="") as f:
                for r in csv.DictReader(f):
                    try:
                        t = datetime.fromisoformat(r["timestamp"])
                    except (KeyError, ValueError):
                        continue
                    if start <= t <= end:
                        r["_t"] = t
                        out.append(r)
        except OSError:
            pass
        day += timedelta(days=1)
    out.sort(key=lambda r: r["_t"])
    return out


def evaluate(test, log_dir=None, now=None):
    """Judge one test dict (state/started/ends/settings). Returns a plain dict."""
    log_dir = log_dir or loop_state.LOGS
    now = now or datetime.now()
    s = dict(loop_state.DEFAULT_SETTINGS)
    s.update(test.get("settings", {}))
    res = {"state": test.get("state", "idle"), "settings": s, "verdict": "NO TEST",
           "breaches": {}, "events": []}
    if not test.get("started"):
        return res

    start = datetime.fromisoformat(test["started"])
    ends = datetime.fromisoformat(test["ends"])
    stop = None
    if test.get("state") in ("stopped", "aborted") and test.get("stopped"):
        stop = datetime.fromisoformat(test["stopped"])
    window_end = min(x for x in (now, ends, stop) if x is not None)
    finished = now >= ends and test.get("state") not in ("stopped", "aborted")
    rows = _rows(log_dir, start, window_end)

    breaches = res["breaches"]

    def breach(rule, t, detail):
        if rule not in breaches:
            breaches[rule] = {"time": t.isoformat(timespec="seconds"), "detail": detail}

    def event(t, text):
        if len(res["events"]) < 50:
            res["events"].append({"time": t.isoformat(timespec="seconds"), "text": text})

    max_cpu = max_gpu = max_mem = None
    displayed = lost = 0
    prev = None
    stall = 0
    playing_seen = False
    for r in rows:
        t = r["_t"]
        cpu, gpu, mem = _f(r.get("cpu_temp_c")), _f(r.get("gpu_temp_c")), _f(r.get("mem_used_pct"))
        if cpu is not None:
            max_cpu = cpu if max_cpu is None else max(max_cpu, cpu)
            if cpu >= s["max_temp_c"]:
                breach("temperature", t, f"CPU reached {cpu:.1f} °C")
        if gpu is not None:
            max_gpu = gpu if max_gpu is None else max(max_gpu, gpu)
            if gpu >= s["max_temp_c"]:
                breach("temperature", t, f"GPU reached {gpu:.1f} °C")
        if mem is not None:
            max_mem = mem if max_mem is None else max(max_mem, mem)
            if mem >= s["max_mem_pct"]:
                breach("memory", t, f"memory use reached {mem:.1f}%")
        displayed += int(_f(r.get("displayed_delta")) or 0)
        lost += int(_f(r.get("lost_delta")) or 0)

        if s["require_uptime"]:
            if prev is not None:
                up, pup = _f(r.get("uptime_s")), _f(prev.get("uptime_s"))
                gap = (t - prev["_t"]).total_seconds()
                if up is not None and pup is not None and up < pup:
                    breach("uptime", t, "the Pi restarted")
                    event(t, "Pi restarted")
                elif gap > GAP_S:
                    breach("uptime", t, f"no record for {gap:.0f} s")
                    event(t, f"recording gap of {gap:.0f} s")
            now_playing = r.get("vlc_ok") == "1" and r.get("vlc_state") == "playing"
            if not playing_seen:
                if now_playing:
                    playing_seen = True
                    if (t - start).total_seconds() > 60:
                        event(t, f"video started {(t - start).total_seconds():.0f} s after the test began")
                elif (t - start).total_seconds() > STARTUP_S:
                    playing_seen = True  # start-up is over; from here a stop counts
                    breach("uptime", t, f"the video did not start within {STARTUP_S // 60} minutes")
                    event(t, "video did not start")
                prev = r
                continue
            if r.get("vlc_restart") == "1":
                breach("uptime", t, "the video player restarted")
                event(t, "video player restarted")
            if r.get("vlc_ok") != "1" or r.get("vlc_state") != "playing":
                stall += 1
                if stall == STALL_SAMPLES:  # brief blips at a loop boundary are allowed
                    breach("uptime", t, f"video not playing ({r.get('vlc_state') or 'no answer'})")
                    event(t, f"video not playing ({r.get('vlc_state') or 'no answer'})")
            else:
                stall = 0
        prev = r

    # Coverage: the start of the window and the time since the last record.
    if s["require_uptime"]:
        if rows and (rows[0]["_t"] - start).total_seconds() > START_GRACE_S:
            breach("uptime", rows[0]["_t"], "no record at the start of the test")
        tail = (window_end - rows[-1]["_t"]).total_seconds() if rows else (window_end - start).total_seconds()
        if tail > max(GAP_S, START_GRACE_S if not rows else 0):
            t = rows[-1]["_t"] if rows else start
            breach("uptime", t, f"no record for the last {tail:.0f} s")

    total = displayed + lost
    drop_pct = (100.0 * lost / total) if total else None
    if finished and drop_pct is not None and drop_pct >= s["max_drop_pct"]:
        breach("frames", window_end, f"{lost} of {total} frames dropped")

    elapsed = (window_end - start).total_seconds()
    needed = (ends - start).total_seconds()
    res.update(
        started=test["started"], ends=test["ends"], samples=len(rows),
        elapsed_h=round(elapsed / 3600, 2), needed_h=round(needed / 3600, 2),
        progress=round(min(1.0, elapsed / needed), 4) if needed else 0.0,
        max_cpu_c=max_cpu, max_gpu_c=max_gpu, max_mem_pct=max_mem,
        displayed=displayed, lost=lost, drop_pct=drop_pct,
        drop_over_now=bool(drop_pct is not None and drop_pct >= s["max_drop_pct"]),
    )
    if not rows:
        res["verdict"] = "NO DATA" if elapsed > START_GRACE_S else "STARTING"
    elif finished:
        res["verdict"] = "FAIL" if breaches else "PASS"
    elif test.get("state") in ("stopped", "aborted"):
        res["verdict"] = "STOPPED"
    else:
        res["verdict"] = "FAILING" if breaches else "RUNNING"
    return res


def current(log_dir=None):
    """Evaluate the test recorded in burnin.json. Marks a finished test as passed/failed there."""
    b = loop_state.burnin()
    t = b["test"]
    if t.get("state") == "pending_restart":
        return {"state": "pending_restart", "verdict": "WAITING FOR RESTART", "settings": t.get("settings", b["settings"]),
                "breaches": {}, "events": []}
    res = evaluate(t, log_dir)
    if t.get("state") == "running" and res["verdict"] in ("PASS", "FAIL"):
        t = dict(t, state="finished", verdict=res["verdict"],
                 breaches=res["breaches"], finished=loop_state.now_iso())
        try:
            loop_state.save_burnin(test=t)
        except OSError:
            pass
        res["state"] = "finished"
    elif t.get("state") == "finished":
        res["verdict"] = t.get("verdict", res["verdict"])
    return res


def last_pass():
    """True if the most recent finished test passed."""
    t = loop_state.burnin()["test"]
    return t.get("state") == "finished" and t.get("verdict") == "PASS"


RULE_NAMES = {"temperature": "Temperature", "memory": "Memory", "frames": "Dropped frames", "uptime": "Uptime"}


def fmt_hours(h):
    whole = int(h)
    return f"{whole} h {int(round((h - whole) * 60)):02d} min"


def report(res):
    s = res["settings"]
    lines = [f"Verdict: {res['verdict']}"]
    if "started" in res:
        lines.append(f"Test: {fmt_hours(res['elapsed_h'])} of {res['needed_h']:g} h "
                     f"({100 * res['progress']:.0f}%), started {res['started'].replace('T', ' ')}")
        def val(v, unit):
            return "—" if v is None else f"{v:.1f}{unit}"
        lines.append(f"Highest CPU {val(res['max_cpu_c'], ' °C')}, GPU {val(res['max_gpu_c'], ' °C')} "
                     f"(limit below {s['max_temp_c']:g} °C)")
        lines.append(f"Highest memory use {val(res['max_mem_pct'], '%')} (limit below {s['max_mem_pct']:g}%)")
        dp = "—" if res["drop_pct"] is None else f"{res['drop_pct']:.5f}%"
        lines.append(f"Dropped frames {res['lost']:,} of {res['displayed'] + res['lost']:,} = {dp} "
                     f"(limit below {s['max_drop_pct']:g}%, judged at the end)")
        lines.append("Uptime rule: " + ("on (no restarts, gaps or stops)" if s["require_uptime"] else "off"))
    for rule, b in res["breaches"].items():
        lines.append(f"FAILED {RULE_NAMES.get(rule, rule)} at {b['time'].replace('T', ' ')}: {b['detail']}")
    return "\n".join(lines)


if __name__ == "__main__":
    r = current()
    print(json.dumps(r, indent=2, default=str) if "--json" in sys.argv else report(r))
