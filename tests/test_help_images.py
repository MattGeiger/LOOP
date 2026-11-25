# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every screenshot a Help guide shows exists in src/help/images (made by sim/help/make_help_images.py), except
the ones that must be captured on a Pi desktop and are listed in PENDING until they are.
Run: python3 tests/test_help_images.py
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HELP = os.path.join(ROOT, "src", "help")
PENDING = set()  # pictures that must still be captured on a Pi desktop (none now)

missing, pending = [], []
for name in sorted(os.listdir(HELP)):
    if not name.endswith(".md"):
        continue
    for ref in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", open(os.path.join(HELP, name)).read()):
        if not os.path.isfile(os.path.join(HELP, ref)):
            (pending if ref in PENDING else missing).append(f"{name}: {ref}")
for m in missing:
    print("FAIL missing " + m)
for p in pending:
    print("note pending Pi capture " + p)
print("all passed" if not missing else f"{len(missing)} missing")
sys.exit(1 if missing else 0)
