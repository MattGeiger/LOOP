#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""loop-idle-video: turn an idle-screen picture into a short H.264 video (installed as /usr/bin/loop-idle-video).

VLC showing a still picture redraws it in software and runs the Pi hotter, with more power, than playing an
H.264 video, which the Pi decodes in hardware. So LOOP always plays the idle screen as a video: a 60-second loop
at 2 frames per second, 1920 x 1080 (the picture is scaled to fit and centred on the theme's background colour,
never stretched), no sound. A still picture compresses to a few hundred kilobytes.

  loop-idle-video picture.png [-o out.mp4] [--rotate 0|90|180|270] [--seconds 60]
      Convert one picture. --rotate turns it clockwise first (for a TV mounted on its side or upside down;
      the Pi's own output always stays landscape). Also writes a matching still (.png) for the desktop.
  loop-idle-video --auto [--force]
      For this display (run by loop-setup as root): make the idle video for its rotation from the profile's
      idle art, into /var/lib/loop/idle. Skipped when the video is already newer than the picture.
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_profile  # noqa: E402

WIDTH, HEIGHT, FPS, SECONDS = 1920, 1080, 2, 60
TURN = {0: [], 90: ["transpose=clock"], 180: ["hflip", "vflip"], 270: ["transpose=cclock"]}


def filters(rotate, background):
    color = "0x" + background.lstrip("#")
    return ",".join(TURN[rotate] + [
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease",
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color={color}",
        "format=yuv420p"])


def convert(src, out, rotate=0, seconds=SECONDS, background=None):
    """Write out (MP4) and a still next to it (same name, .png). Returns out."""
    if rotate not in TURN:
        raise SystemExit(f"loop-idle-video: --rotate must be 0, 90, 180 or 270 (not {rotate})")
    if not os.path.isfile(src):
        raise SystemExit(f"loop-idle-video: no picture at {src}")
    if not shutil.which("ffmpeg"):
        raise SystemExit("loop-idle-video: ffmpeg is not installed")
    background = background or loop_profile.theme().get("bg_start", "#000000")
    vf = filters(rotate, background)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".part.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", src,
                    "-t", str(seconds), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage",
                    "-crf", "18", "-profile:v", "high", "-level", "4.0", "-r", str(FPS),
                    "-movflags", "+faststart", "-an", tmp], check=True)
    os.replace(tmp, out)
    still = os.path.splitext(out)[0] + ".png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", vf.replace(",format=yuv420p", ""),
                    "-frames:v", "1", "-update", "1", still], check=True)
    for f in (out, still):
        os.chmod(f, 0o644)
    return out


def auto(force=False):
    rot = loop_profile.display()["rotate"]
    src = loop_profile.idle_source(rot)
    if not src:
        print("loop-idle-video: the profile has no idle picture; the packaged idle screen is used")
        return 0
    out = loop_profile.idle_generated(rot)
    if not force and os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        print(f"loop-idle-video: idle video up to date ({os.path.basename(out)}, rotated {rot}°)")
        return 0
    convert(src, out, rot)
    for old in os.listdir(loop_profile.IDLE_DIR):  # videos made for an earlier rotation
        if old.startswith("idle-screen-r") and not old.startswith(f"idle-screen-r{rot}."):
            os.remove(os.path.join(loop_profile.IDLE_DIR, old))
    print(f"loop-idle-video: made {out} from {os.path.basename(src)} (rotated {rot}°, "
          f"{os.path.getsize(out) // 1024} KB)")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="loop-idle-video", description=__doc__.split("\n\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("picture", nargs="?")
    ap.add_argument("-o", "--output")
    ap.add_argument("--rotate", type=int, default=0, choices=sorted(TURN))
    ap.add_argument("--seconds", type=int, default=SECONDS)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.auto:
        return auto(a.force)
    if not a.picture:
        ap.error("give a picture, or --auto")
    out = a.output or os.path.splitext(a.picture)[0] + (f"-r{a.rotate}" if a.rotate else "") + ".mp4"
    convert(a.picture, out, a.rotate, a.seconds)
    print(f"loop-idle-video: made {out} ({os.path.getsize(out) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
