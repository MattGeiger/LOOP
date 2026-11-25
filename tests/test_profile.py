# SPDX-License-Identifier: AGPL-3.0-or-later
"""loop_profile: defaults, merge order, placeholders, orientation. Run: python3 tests/test_profile.py"""
import json
import os
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, SRC)
import loop_profile as P  # noqa: E402


def with_config(profile=None, site=None):
    d = tempfile.mkdtemp()
    if profile is not None:
        json.dump(profile, open(os.path.join(d, "profile.json"), "w"))
    if site is not None:
        json.dump(site, open(os.path.join(d, "site.json"), "w"))
    os.environ["LOOP_CONFIG_DIR"] = d
    P.load(refresh=True)


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got!r}" + ("" if ok else f" (want {want!r})"))
    return ok


results = []
with_config()
results += [check("no library by default", P.get("content.library_url"), ""),
            check("default data mount", P.data_mount(), "/mnt/loopdata"),
            check("unknown host is landscape", P.display("any-host")["orientation"], "landscape")]
with_config({"identity": {"organization": "Org A", "contact": "Desk"}, "content": {"library_name": "Videos"}},
            {"identity": {"contact": "Pat, IT"}, "content": {"library_url": "https://example.org/v"},
             "displays": {"win": {"orientation": "portrait-cw"}}})
results += [check("profile value", P.get("identity.organization"), "Org A"),
            check("site overrides profile", P.get("identity.contact"), "Pat, IT"),
            check("defaults kept on merge", P.get("content.keep_videos"), 3),
            check("site library url", P.get("content.library_url"), "https://example.org/v"),
            check("portrait host", P.display("win")["orientation"], "portrait-cw"),
            check("fill placeholders", P.fill("Open {{content.library_name}}; ask {{identity.contact}}."),
                  "Open Videos; ask Pat, IT."),
            check("unknown placeholder kept", P.fill("{{nope.key}}"), "{{nope.key}}")]
d = tempfile.mkdtemp()
open(os.path.join(d, "profile.json"), "w").write("{ not json")
os.environ["LOOP_CONFIG_DIR"] = d
P.load(refresh=True)
results.append(check("broken file falls back to defaults", P.get("identity.contact"), "the person who looks after the displays"))
sys.exit(0 if all(results) else 1)
