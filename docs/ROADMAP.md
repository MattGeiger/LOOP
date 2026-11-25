# LOOP roadmap

## 1.0

- Zero-touch playback of the newest video on the USB data drive, with a backup video and a branded idle screen.
- Staff Display Tools: mouse-only, instant feedback, Help with screenshots, Display status, Performance History.
- Setup Mode with configurable burn-in tests, Go Live, and Update Software with read-only mode around it.
- Profiles and site files for any organization, a setup wizard and Settings, WCAG 2.2 contrast checks with
  readable-shade suggestions.
- A Debian package that installs and removes cleanly, and a Pi Imager image with LOOP's boot screen.
- Tests and CI on every push.

## 1.1.0 (planned)

A shared visual language: Lucide icons on every interactive control, clickable LOOP Setup steps, and consistent
wording. See [DESIGN_LANGUAGE.md](DESIGN_LANGUAGE.md) for the icon table, the rules, and the renamed controls.

- An icon table in code, read by Staff Display Tools, LOOP Setup, Settings, Setup & burn-in and Update Software.
- Lucide SVGs bundled in `src/icons/`, drawn in each control's text color at the window's scale, with a spinner
  while a control is busy. Lucide is credited in About.
- LOOP Setup steps become clickable. A step opens once the step before it is complete; until then it is muted and
  ignores clicks.
- Update Software's steps get icons and new names, and stay non-clickable progress markers.
- Renamed controls in sentence case. Help, the Help pictures and the README pictures are updated to match.
- `test_contrast.py` checks icons for WCAG's 3:1 contrast.

## After 1.0

- **Settings:** burn-in default limits, advanced data-drive options, and removing one picture to go back to the
  profile's.
- **Idle art for a sideways TV:** ask for portrait art in the wizard when a display's rotation is 90 or 270
  (today landscape art is turned and letterboxed).
- **USB data drive:** if the drive resets (for example when a device is plugged into the port beside it), the
  display stays on its idle screen until a restart. Possible work: reconnect the drive automatically and say so
  in Staff Display Tools.
- **Screens narrower than 1280 px:** windows keep their 1280×720 design, so smaller screens cut off the right side.
- **Docs:** generate a printable staff guide from the Help Markdown; an administrator guide.
- **Cleanup:** retire the original install scripts (`src/install*.sh`) and the older `sim/vm` test bench in favour
  of the package and `sim/pios`; reorganize `src/` into packages.
