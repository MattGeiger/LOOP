# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fails if organization-specific text is hard-coded in src/. It belongs in a profile or site file.
Run: python3 tests/test_no_org_strings.py"""
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
BANNED = re.compile(r"william\s*temple|\bwth\b|wth[-_]|wthdata|thrift|sharepoint|ts-display|williamtemple|1965",
                    re.IGNORECASE)
ALLOWED = ("Matt Geiger, Temple Consulting",)  # LOOP's own creator credit
hits = []
for root, _, files in os.walk(SRC):
    for name in files:
        path = os.path.join(root, name)
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            if BANNED.search(line) and not any(a in line for a in ALLOWED):
                hits.append(f"{os.path.relpath(path, SRC)}:{n}: {line.strip()[:100]}")
print("\n".join(hits) if hits else "ok: no organization-specific text in src/")
sys.exit(1 if hits else 0)
