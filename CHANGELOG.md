# Changelog

All notable changes to LOOP. Versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] · 2026-11-25

A shared visual language for every window: icons with fixed meanings, clickable setup steps, and consistent
wording. [docs/DESIGN_LANGUAGE.md](docs/DESIGN_LANGUAGE.md) describes it.

### Added

- Lucide icons on every button, card, link, step and tab, from one icon table (`src/ui_icons.py`). Each icon is
  drawn in its control's text color at the window's scale, and a spinning loader replaces it while a control
  works. The icons are bundled in `src/icons/` (Lucide 1.80.0; GitHub from 1.0.0; ISC License), and Lucide is
  credited in About.
- LOOP Setup's steps are clickable. Completed steps open again; a step opens only once the one before it is
  complete, and later steps are muted and ignore clicks.
- Settings tabs and Update Software's steps show the same icons. Update Software's steps stay progress markers.
- Tests: `test_icons.py` keeps the icon table, the bundled icons and the design document in step;
  `test_contrast.py` checks icon colors for 3:1 contrast.

### Changed

- Renamed: **Done – back to fullscreen** is now **Start fullscreen playback**; **Finish Setup (Go Live)** is now
  **Finish setup (go live)**; **Performance History** is now **Performance history**; the **Setup & burn-in**
  button is now **Setup & Burn-in**.
- Update Software's steps are now **Read/write Mode**, **Check for updates**, **Set Read-only Mode** and
  **Return to video**.
- Update Software's buttons:
  - **Enable Read-Only Mode** is now **Set Read-only Mode**.
  - **Skip updates – Enable Read-Only Mode** is now **Skip updates & set Read-only Mode**.
  - **Finish – resume video** is now **Cancel** on the update step and **Done** when updates are finished.
  - **Check For Updates** is now **Check for updates**, and **Update All** is now **Update all**.
- Wording is in sentence case, apart from a short list of proper terms (for example Read-only Mode and Setup
  Mode).

## [1.0.0] · 2026-11-25

First release.

### Playback

- VLC starts at login and loops the newest finished video in the data drive's `videos` folder. Partial downloads
  are ignored, and a new video starts when the current loop ends.
- Fallback chain: the newest USB video, then a backup video, then the idle screen.
- The idle screen plays as a 60-second H.264 video made from a picture, turned 0, 90, 180 or 270 degrees for the
  display's mounting.
- The player pauses and leaves fullscreen while Staff Display Tools is open, and resumes afterwards. It returns to
  fullscreen two minutes after someone leaves it.

### Staff Display Tools

- A mouse-only control window: Get a new video, Open videos folder, Show idle screen, Restart video, Display status,
  Performance History, Help, About, Release Notes and Settings.
- Instant feedback on every click; repeat clicks are ignored while an action runs.
- Help guides in Markdown with screenshots, filled in from the profile and site settings.
- One 1280×720 layout, scaled for 1080p and 4K.

### Setup and maintenance

- The LOOP Setup wizard opens at the first login, and the same pages are available later as Settings. They cover
  the organization, video library link, display mounting, the USB data drive, pictures and colors. Everything is
  checked before saving with the administrator password.
- Setup Mode: a burn-in test with a configurable length and limits for temperature, memory, dropped frames and
  uptime, judged automatically. A finished or failed test can be changed and rerun. **Finish Setup (Go Live)**
  completes setup.
- Read-only mode keeps the operating system on the SD card read-only (overlayroot with `recurse=0`). Videos, state
  and Performance History are written directly to the USB data drive.
- Update Software switches to read/write mode, installs updates, and returns to read-only mode, with the video held
  on the idle screen throughout.
- Performance History records temperatures, throttling, memory and VLC frame statistics every 5 seconds.

### Profiles and appearance

- Organization settings live in `profile.json` (identity and theme) and `site.json` (deployment settings), with
  `basedOn` to start from a packaged profile. No organization text is hard-coded in `src/`.
- WCAG 2.2 contrast checks, with one-click readable-shade suggestions (OKLCH) and a custom two-tone background.
- The desktop, wallpaper, title bars, taskbar colors and boot screen follow the profile. Taskbar colors are written
  to a user copy of the Pi OS theme, so they survive restarts.

### Packaging

- `loop-display` Debian package for Raspberry Pi OS (trixie): install, `loop-setup`, and removal that restores the
  desktop user's settings.
- Pi Imager image built from the official Raspberry Pi OS image, with a `cloudinit-rpi` repository file so Imager's
  OS customisation works.
- Locked-down Chromium: private windows only, downloads go to the data drive, a library bookmark, and no keyring
  prompt.

### Development

- Unit tests, a GTK window smoke test, and CI on every push.
- A Docker GTK screenshot bench that also generates the Help pictures.
- Raspberry Pi OS virtual machines for whole-system tests.
