#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make the Help screenshots in src/help/images from the Docker window screenshots.

Help shows pictures at most 600 px wide, so each one is cropped to what its step is about, and the control the
step mentions is outlined in LOOP's orange. Positions come from rects.json, written by the screenshot harness, so the
pictures follow the windows when they change. LOOP's own look (profiles/default) is used, never an organization's.

  docker run --rm -e LOOP_SCREEN=1280x720 -e LOOP_SHOTS=/loop/sim/out/help -v "$PWD":/loop -w /loop \\
      loop-ui-test sh sim/docker/run.sh
  python3 sim/help/make_help_images.py            (reads sim/out/help, writes src/help/images)
"""
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "sim", "out", "help")
OUT = os.path.join(ROOT, "src", "help", "images")
ORANGE = (231, 148, 64)
MAX_W = 1200  # stored at up to 2x Help's 600 px, so they stay sharp on a 1080p screen

rects = json.load(open(os.path.join(SRC, "rects.json")))


def outline(im, r, pad=7, width=4):
    x, y, w, h = r
    ImageDraw.Draw(im).rounded_rectangle([x - pad, y - pad, x + w + pad, y + h + pad], radius=12, outline=ORANGE,
                                         width=width)


def make(name, shot, crop=None, marks=()):
    im = Image.open(os.path.join(SRC, shot + ".png")).convert("RGB")
    for mark in marks:
        outline(im, rects[shot][mark])
    if crop:
        im = im.crop(crop)
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    im.save(os.path.join(OUT, name), optimize=True)
    print(f"{name:24} {im.width}x{im.height}  from {shot}")


def rows(shot, top_mark, bottom_mark, above=60, below=40):
    """A crop from just above one control to just below another, the full window width."""
    w = Image.open(os.path.join(SRC, shot + ".png")).width
    t, b = rects[shot][top_mark], rects[shot][bottom_mark]
    return (0, max(0, t[1] - above), w, b[1] + b[3] + below)


os.makedirs(OUT, exist_ok=True)
make("main-window.png", "main-window")
make("restart-confirm.png", "restart-confirm", rows("restart-confirm", "restart", "restart", 140, 30),
     marks=["restart"])
make("up-next.png", "main-window", rows("main-window", "now", "next", 50, 14), marks=["next"])
make("warning.png", "help-warning", rows("help-warning", "now", "warn", 50, 14), marks=["warn"])
make("display-status.png", "display-status")
make("update-software.png", "update-software")
make("setup-burnin.png", "setup-burnin")
make("settings.png", "settings-library")
make("setup-wizard.png", "wizard-0-start")
make("wizard-colors.png", "wizard-5-colors-suggestion")
