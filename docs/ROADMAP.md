# LOOP roadmap

## 1.0

- Zero-touch playback of the newest video on the USB data drive, with a backup video and a branded idle screen.
- Staff Display Tools: mouse-only, instant feedback, Help with screenshots, Display status, Performance History.
- Setup Mode with configurable burn-in tests, Go Live, and Update Software with read-only mode around it.
- Profiles and site files for any organization, a setup wizard and Settings, WCAG 2.2 contrast checks with
  readable-shade suggestions.
- A Debian package that installs and removes cleanly, and a Pi Imager image with LOOP's boot screen.
- Tests and CI on every push.

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
