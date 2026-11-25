# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Burn-in evaluator scenarios on synthetic Performance history logs. Run: python3 tests/test_eval_scenarios.py"""
import csv, sys, os
from datetime import datetime, timedelta
import tempfile
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, SRC); import burnin_eval as E, burnin_logger as L
D = tempfile.mkdtemp()
def make(hours, tweak=lambda i,r:None):
    for f in os.listdir(D): os.remove(os.path.join(D,f))
    start = datetime(2026,11,20,22,0,0)
    n = int(hours*3600/5)
    for i in range(n+1):
        t = start + timedelta(seconds=5*i)
        r = dict.fromkeys(L.FIELDS,""); r.update(timestamp=t.isoformat(), uptime_s=1000+5*i, cpu_temp_c=60, gpu_temp_c=60.5,
            mem_used_pct=30, vlc_restart=0, vlc_ok=1, vlc_state="playing", displayed_delta=150, lost_delta=0)
        tweak(i, r)
        if r.get("_skip"): continue
        p = os.path.join(D, f"burnin-{t:%Y-%m-%d}.csv"); new = not os.path.exists(p)
        with open(p,"a",newline="") as f:
            w = csv.DictWriter(f, L.FIELDS, extrasaction="ignore"); new and w.writeheader(); w.writerow(r)
    return {"state":"running","started":start.isoformat(),"ends":(start+timedelta(hours=24)).isoformat(),"settings":{"hours":24}}, start
FAILS = []
def run(name, hours, tweak=lambda i,r:None, now_h=None, expect=None, **st):
    t, start = make(hours, tweak); t["settings"].update(st)
    r = E.evaluate(t, D, now=start+timedelta(hours=now_h if now_h is not None else hours, seconds=1))
    ok = expect is None or r["verdict"] == expect
    FAILS.extend([] if ok else [name])
    print(f"{'ok  ' if ok else 'FAIL'} {name:34} {r['verdict']:8} {list(r['breaches'])} drop={r['drop_pct']}")
run("clean full day", 24, expect="PASS")
run("clean half day", 12, expect="RUNNING")
run("hot GPU", 24, lambda i,r: r.update(gpu_temp_c=80.0) if i==5000 else None, expect="FAIL")
run("hot GPU, limit 85", 24, lambda i,r: r.update(gpu_temp_c=80.0) if i==5000 else None, max_temp_c=85, expect="PASS")
run("memory", 24, lambda i,r: r.update(mem_used_pct=81) if i==100 else None, expect="FAIL")
run("drops 1/100k ok? (=0.001)", 24, lambda i,r: r.update(lost_delta=1) if i%667==0 else None, expect="FAIL")
run("drops few", 24, lambda i,r: r.update(lost_delta=1) if i==10 else None, expect="PASS")
run("reboot", 24, lambda i,r: r.update(uptime_s=50) if i==9000 else None, expect="FAIL")
run("gap", 24, lambda i,r: r.update(_skip=1) if 9000<=i<9010 else None, expect="FAIL")
run("gap, uptime off", 24, lambda i,r: r.update(_skip=1) if 9000<=i<9010 else None, require_uptime=False, expect="PASS")
run("vlc paused", 24, lambda i,r: r.update(vlc_state="paused") if i==300 else None, expect="PASS")
run("recorder died at 10h", 10, now_h=12, expect="FAILING")
run("vlc 1 blip", 24, lambda i,r: r.update(vlc_state="stopped") if i==300 else None, expect="PASS")
run("vlc stopped 20s", 24, lambda i,r: r.update(vlc_state="stopped") if 300<=i<304 else None, expect="FAIL")
# Start-up: the test begins at boot, before the player has started.
boot = lambda i, r: r.update(vlc_ok=0, vlc_state="") if i < 12 else (r.update(vlc_restart=1) if i == 12 else None)
run("start-up: video after 60 s", 24, boot, expect="PASS")
run("start-up: video never starts", 24, lambda i, r: r.update(vlc_ok=0, vlc_state=""), expect="FAIL")
run("start-up: stop after it started", 24, lambda i, r: boot(i, r) or (r.update(vlc_state="stopped") if 100 <= i < 104 else None), expect="FAIL")
print("all passed" if not FAILS else f"{len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
