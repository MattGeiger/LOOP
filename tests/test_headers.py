# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Every LOOP source file carries the AGPL-3.0-or-later licence header (SPDX). Run: python3 tests/test_headers.py"""
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
files = subprocess.run(["git", "ls-files", "*.py", "*.sh", "packaging/DEBIAN/postinst", "packaging/DEBIAN/prerm",
                        "packaging/DEBIAN/postrm"], cwd=ROOT, capture_output=True, text=True).stdout.split()
missing = [f for f in files if "SPDX-License-Identifier: AGPL-3.0-or-later" not in open(os.path.join(ROOT, f)).read(600)]
for f in missing:
    print("FAIL no licence header: " + f)
print(f"{len(files)} files checked; " + ("all passed" if not missing else f"{len(missing)} missing"))
sys.exit(1 if missing else 0)
