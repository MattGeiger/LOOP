# LOOP — Local Outreach on Pi

LOOP turns a Raspberry Pi and a TV into a dependable outreach display. The Pi plays your organization's
video on a loop by itself, through restarts, power cuts and internet outages. Staff change the video and check
the display from anywhere through Raspberry Pi Connect, using a simple, mouse-only control window.

LOOP is part of the same family as LOTTO and FEED, by Matt Geiger, Temple Consulting, LLC.

> **Version 1.0.** Nothing organization-specific is written into the code; it comes from a profile and a site
> file (below). [CHANGELOG.md](CHANGELOG.md) lists what's in each release and [docs/ROADMAP.md](docs/ROADMAP.md)
> what's next.

## What it does

- **Zero-touch playback.** VLC starts at boot and loops the newest video from a USB drop folder. A new
  video starts when the current loop ends; a backup video and a branded idle screen cover a missing drive or file.
- **Manual, human-chosen content.** Staff download each video from the organization's video library (any web
  link: SharePoint, Google Drive, a website) in a locked-down private browser. Nothing is pushed to the screen
  automatically.
- **Staff Display Tools.** Get a new video, open the videos folder, show the idle screen, restart the video,
  display status, Performance History, Help and About, with instant click feedback.
- **Performance History.** Every 5 seconds: temperatures, throttling, memory and VLC frame statistics, kept
  7+ days in Setup Mode and 24 hours in Production Mode.
- **Setup Mode and burn-in.** A configurable test (12–96 h; temperature, memory, dropped-frame and uptime
  limits) judged automatically, then **Finish Setup (Go Live)**.
- **Read-only operation.** The OS runs read-only so power cuts cannot corrupt it; videos, state and history live
  on the USB drive. **Update Software** handles the read/write window with the administrator password.

## Configuration

Two JSON files, read by [src/loop_profile.py](src/loop_profile.py), which lists every setting and its default:

| File | Holds | Where it lives |
| --- | --- | --- |
| `profile.json` | The organization's identity: name, website, how staff refer to the displays, desktop icon name, colors, video library name, branding notice | `profiles/<org>/` in this repo (LOOP's default, TemplePDX look: [profiles/default](profiles/default/profile.json)) |
| `site.json` | One deployment's private settings: the **video library link**, staff contact, each display's hostname, orientation and `rotate` (0, 90, 180 or 270), the data drive | The organization's private repository, never here ([example](profiles/default/site.example.json)) |

On a Pi both go in `~/loop/` (or `/etc/loop/`). Help guides use `{{dotted.key}}` placeholders filled from these
files. A missing file or setting falls back to a neutral default, and `tests/test_no_org_strings.py` fails if an
organization name, link or hostname is written into `src/`.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/` | Player, Performance History, Staff Display Tools, admin windows, Help guides, privileged helper, setup scripts |
| `profiles/wth/` | William Temple House profile and branding assets (not open source; see TRADEMARKS.md) |
| `profiles/default/` | LOOP's default profile: TemplePDX.com branding (Twilight Ember), used when no organization profile is installed, plus an example site file |
| `assets/temple/` | Temple Consulting logo for the About window |
| `packaging/` | Debian package and Pi Imager image builds |
| `sim/` | Test benches: Docker window screenshots and Raspberry Pi OS virtual machines |
| `tests/` | Unit tests and a Staff Tools window smoke test (no Pi or GTK needed); run on every push |
| `docs/` | Roadmap and the hardware validation checklist |

## Requirements

Raspberry Pi 4 (2 GB is enough) or newer, Raspberry Pi OS (trixie) with the desktop, a USB drive for data, and
Raspberry Pi Connect for remote access. Don't plug devices into the USB ports while a display plays: a new
device in the port beside the data drive can reset the drive, and the display then shows its idle screen until
a restart.

## Themes and accessibility

Staff Display Tools takes every color from the profile's `theme`. LOOP's default theme follows TemplePDX.com
(Temple Consulting wordmark, "Twilight Ember" palette); organizations supply their own in their profile, or start
from a packaged one with `{"basedOn": "<name>"}`. Every theme must pass `tests/test_contrast.py` (WCAG 2.2 text
and component contrast, minimum text and target sizes).

Every window is designed for a 1280×720 screen and scaled for larger 16:9 screens (1.5× at 1080p, 3× at 4K), so
it looks the same on any HD television. Below 720p only the middle of a window scrolls; its buttons stay in view.

## Setup wizard and Settings

After `apt install`, **LOOP Setup** opens at the next login (or from the menu, or `loop-setup-wizard`). It asks for
the organization's details, the video library link, how the TV is mounted, the data drive, pictures and colors,
checks everything (including WCAG contrast) and saves with the administrator password. The same pages are in
Staff Display Tools > **Settings** for later changes. Both write the same two files through `loop-setup`.

## Idle screen

The idle screen always plays as a short H.264 video, because VLC showing a still picture runs the Pi hotter.
`loop-setup` makes it from the profile's idle picture (or your own: `--idle-image`, and `--idle-portrait` for a TV
on its side), turned by the display's `rotate` setting. To convert a picture by hand:

```bash
loop-idle-video picture.png --rotate 90
```

## Pi Imager image

```bash
packaging/build-pi-image.sh 2026-10-06-raspios-trixie-arm64.img.xz [profile ...]
```

Builds `dist/loop-pios_<version>_arm64.img.xz` from the official Raspberry Pi OS (64-bit) image with LOOP installed.
Write it with Raspberry Pi Imager (**Use custom**), with OS customisation as usual; LOOP Setup opens at the first
login. See [docs/HARDWARE_VALIDATION.md](docs/HARDWARE_VALIDATION.md).

## Package

```bash
packaging/build-deb.sh [profile ...]
```

On the Pi, one admin command installs and sets up a display:

```bash
sudo sh -c 'apt install ./loop-display_*_all.deb && loop-setup --profile <profile> --site site.json --drive /dev/sda --erase-drive'
```

`sudo apt remove loop-display` puts the display user's own settings back as they were before setup (VLC,
Chromium bookmarks and downloads, taskbar, desktop look), except anything changed since. `purge` also deletes
LOOP's settings and backup video. Videos on the USB drive are never touched.

## Tests

```bash
for t in tests/test_*.py tests/smoke_ui.py; do python3 "$t" || break; done
```

The same suite runs on GitHub Actions for every push. Window screenshots and Help pictures come from the Docker
bench in `sim/docker`; whole-system tests use the Raspberry Pi OS virtual machines in `sim/pios` (see
[sim/README.md](sim/README.md)).

## License

Code: [AGPL-3.0-or-later](LICENSE). William Temple House and Temple Consulting names and assets are excluded; see
[TRADEMARKS.md](TRADEMARKS.md).
