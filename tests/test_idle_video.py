# SPDX-License-Identifier: AGPL-3.0-or-later
"""loop-idle-video: a still picture becomes a 60-second, 2 fps, 1920x1080 H.264 video, turned clockwise by the
chosen rotation. Needs ffmpeg and Pillow. Run: python3 tests/test_idle_video.py
"""
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageChops, ImageStat

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ["LOOP_CONFIG_DIR"] = tempfile.mkdtemp()  # LOOP's default theme, no site settings
import loop_idle_video  # noqa: E402
import loop_profile  # noqa: E402

fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                          "stream=codec_name,profile,width,height,r_frame_rate,pix_fmt:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    return j["streams"][0], float(j["format"]["duration"])


tmp = tempfile.mkdtemp()
portrait = os.path.join(ROOT, "profiles", "default", "idle-screen-portrait.png")  # 1080 x 1920
landscape = os.path.join(ROOT, "profiles", "default", "idle-screen.png")
for rot, src in ((0, landscape), (90, portrait), (180, landscape), (270, portrait)):
    out = loop_idle_video.convert(src, os.path.join(tmp, f"r{rot}.mp4"), rot)
    st, dur = probe(out)
    check(st["codec_name"] == "h264" and st["width"] == 1920 and st["height"] == 1080 and st["pix_fmt"] == "yuv420p"
          and st["r_frame_rate"] == "2/1" and abs(dur - 60) < 0.6, f"rotate {rot}: H.264 1920x1080, 2 fps, 60 s")
    still = Image.open(os.path.splitext(out)[0] + ".png").convert("RGB")
    want = Image.open(src).convert("RGB").rotate(-rot, expand=True).resize((1920, 1080))  # PIL turns anticlockwise
    diff = sum(ImageStat.Stat(ImageChops.difference(still, want)).mean) / 3
    check(diff < 6, f"rotate {rot}: picture turned {rot}° clockwise (mean difference {diff:.1f})")
    check(os.path.getsize(out) < 5_000_000, f"rotate {rot}: under 5 MB ({os.path.getsize(out) // 1024} KB)")

# A smaller picture of another shape is centred on the theme background, not stretched.
small = os.path.join(tmp, "square.png")
Image.new("RGB", (600, 600), (255, 255, 255)).save(small)
still = Image.open(os.path.splitext(loop_idle_video.convert(small, os.path.join(tmp, "sq.mp4")))[0] + ".png")
bg = loop_profile.theme()["bg_start"]
bg_rgb = tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))
corner, centre = still.convert("RGB").getpixel((20, 20)), still.convert("RGB").getpixel((960, 540))
check(max(abs(a - b) for a, b in zip(corner, bg_rgb)) < 6 and centre == (255, 255, 255),
      "other shapes: scaled to fit and centred on the theme background")

# Each display's rotation: from "rotate", or from its orientation.
os.environ["LOOP_CONFIG_DIR"] = cfg = tempfile.mkdtemp()
json.dump({"displays": {"a": {"orientation": "portrait-cw"}, "b": {"rotate": 270}, "c": {"rotate": 45}, "d": {}}},
          open(os.path.join(cfg, "site.json"), "w"))
json.dump({}, open(os.path.join(cfg, "profile.json"), "w"))
loop_profile._cache = None if hasattr(loop_profile, "_cache") else None
import importlib  # noqa: E402
importlib.reload(loop_profile)
got = {h: loop_profile.display(h)["rotate"] for h in "abcd"}
check(got == {"a": 90, "b": 270, "c": 0, "d": 0}, f"rotation per display {got}")

print("all passed" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
