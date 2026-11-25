# LOOP design language

LOOP's icons and wording form one visual language. Its icons are not decoration. Each one stands for an idea and
means the same thing wherever it appears, so staff learn it once and recognize it on every screen. Check any new
control, window or workflow against this document before adding it. If nothing here fits, extend the system on
purpose (add the meaning, then the icon) rather than picking an icon for one button.

The icon table in code (introduced in 1.1.0) is the single source: Staff Display Tools, LOOP Setup, Settings,
Setup & Burn-in and Update Software all read it, so the same action can't drift to a different icon.

## Icon families

| Family | Meaning | Icons |
| --- | --- | --- |
| **Monitor** | The display itself | `monitor-cog`, `monitor-play`, `monitor-activity`, `monitor` |
| **File** | Content and storage | `file-video-camera`, `folder-open`, `file-cog`, `file-lock` |
| **Cycle** | Software updates | `refresh-cw`, `refresh-cw-off` |
| **Milestones** | One-time steps in setting up a display | `circle-fading-play`, `flame`, `clapperboard`, `circle-dashed-check` |
| **Settings** | Changing configuration | `settings` |
| **Recovery** | Putting something right after a failure | `wrench` (repair), `rotate-ccw` (try again) |

## Icons by action

### Staff Display Tools

| Control | Icon |
| --- | --- |
| Setup & Burn-in | `monitor-cog` |
| Get a new video | `file-video-camera` |
| Open videos folder | `folder-open` |
| Show idle screen | `wallpaper` |
| Restart video (and its "Click again to restart") | `monitor-play` |
| Resume video (the idle screen card, while the idle screen shows) | `monitor-play` |
| Display status | `monitor-activity` |
| Performance history | `list-clock` |
| Update Software | `refresh-cw` |
| Start fullscreen playback | `expand` |
| Version (opens Release Notes) | `rocket` |
| Help | `circle-question-mark` |
| About | `info` |
| Settings | `settings` |

### Setup & Burn-in

| Control | Icon |
| --- | --- |
| Finish setup (go live) | `clapperboard` |
| Go live and restart | `clapperboard` |
| Change settings | `settings` |
| Start burn-in test | `flame` |
| Start another test | `flame` |
| Stop and change settings | `circle-stop` |
| Stop the burn-in test (link) | `circle-stop` |
| Open Settings | `settings` |

### LOOP Setup and Settings (steps and tabs)

| Step | Icon |
| --- | --- |
| Start | `circle-fading-play` |
| Organization | `user-group` |
| Video library | `file-video-camera` (the library is where new videos come from, like **Get a new video**) |
| This display | `monitor` |
| Pictures | `image-plus` |
| Colors | `palette` |
| Review | `circle-dashed-check` |

| Control | Icon |
| --- | --- |
| Start (the wizard's first button) | `circle-fading-play` |
| Open LOOP Setup (step by step) | `circle-fading-play` |
| Look again (USB drive) | `usb` |
| Choose a picture… | `image-plus` |
| Use readable #… | `contrast` |
| Save settings, Save and set up | `save` |

### Update Software

| Step (progress marker) | Icon |
| --- | --- |
| Read/write Mode | `file-cog` |
| Check for updates | `refresh-cw` |
| Set Read-only Mode | `file-lock` |
| Return to video | `monitor-play` |

| Control | Icon |
| --- | --- |
| Check for updates, Check again | `refresh-cw` |
| Open Update Software | `refresh-cw` |
| I understand, switch modes and restart | `file-cog` |
| Skip updates & set Read-only Mode | `refresh-cw-off` |
| Update selected | `list-checks` |
| Update all (N) | `download` |
| Restart now | `power` |
| Repair, Repair and try again | `wrench` |
| Try again | `rotate-ccw` |
| Change settings (Settings window) (link) | `settings` |
| Resume video without read-only (not recommended) (link) | `monitor-play` |
| Cancel, Cancel update | `x` |
| Done | `check` |

### Everywhere

| Control | Icon |
| --- | --- |
| Close, Cancel | `x` |
| Done (finishes a task) | `check` |
| Back / Next / Continue, and Help's Previous / Next | `arrow-left` / `arrow-right` |
| Help's Close and All guides | `x` / `arrow-left` |
| Source Code on GitHub | `github` |
| A button at work | `loader-circle` (spinning) |

### Deliberate pairs and shared icons

- `monitor-play` covers both **Restart video** and **Return to video**: both mean "back to playback".
- `file-video-camera` covers both **Get a new video** and the **Video library** step: both are about the video
  library. `folder-open` is used only for the local videos folder on the USB drive.
- `refresh-cw` means software updates only. The USB **Look again** uses `usb`.
- `monitor-cog` means setting up this display. `settings` means changing values.
- `file-cog` and `file-lock` are the read/write and read-only pair.
- `circle-fading-play` means beginning setup: the wizard's Start step, its Start button, and Open LOOP Setup.
- `wrench` and `rotate-ccw` were added in 1.1.0 for the recovery buttons Update Software already had.

## Rules for icons

- **Always icon plus text.** The only icon without a label is the window close X.
- **Placement:** the icon goes to the left of the label.
- **Size** at the 1280×720 design size, scaled with the window like everything else: 18 px in buttons, 22 px in
  the main window's large cards, 14 px in step pills and tabs.
- **Line:** Lucide's standard 2 px stroke, no fill.
- **Color:**
  - An icon takes its control's text color, including the dark text on yellow primary buttons.
  - Icons must meet WCAG's 3:1 contrast for graphics, which `tests/test_contrast.py` checks.
- **At work:** while a button is busy, a spinning `loader-circle` replaces its icon. This matches the existing
  rule: immediate feedback, and repeat clicks are ignored.
- **Muted:** a control that can't be used yet shows muted (lower contrast, no hover). Clicks on it are ignored.

## Navigation

- **LOOP Setup steps are clickable.**
  - You can always go back to an earlier step.
  - A step opens only once the step before it is complete.
  - Steps not yet reachable look muted and ignore clicks.
- **Settings tabs** are all clickable, since every value already exists. They use the same icons as the wizard
  steps.
- **Update Software steps are progress markers, not buttons.** Each one depends on the display's real state and
  a restart, so they look like pills but aren't clickable.

## Wording

- **Sentence case by default:** "Change settings", "Check for updates", "Finish setup (go live)",
  "Performance history".
- **Title Case only for a few proper terms,** so they stand out:
  - LOOP's names for its modes and windows, for example **Read-only Mode** and **Staff Display Tools**.
  - Brand names such as **Raspberry Pi Connect**.

  When in doubt, ask the maintainer; the list below grows by decision, not by habit.
- **American English spelling:** color, organization, center.

### Proper terms (Title Case)

| Term | Notes |
| --- | --- |
| Staff Display Tools | The control window |
| Setup & Burn-in | The window and its button |
| Setup Mode, Production Mode | The display's two modes |
| LOOP Setup | The setup wizard |
| Read-only Mode, Read/write Mode | Also in "Set Read-only Mode" and "Skip updates & set Read-only Mode" |
| Update Software | The window and its button |
| Raspberry Pi Connect, Raspberry Pi OS, Pi Imager | Brand names |

### Renamed in 1.1.0

| Before | After |
| --- | --- |
| Done – back to fullscreen | Start fullscreen playback |
| Setup & burn-in (button) | Setup & Burn-in |
| Finish Setup (Go Live) | Finish setup (go live) |
| Performance History | Performance history |
| Update steps: 1 Read/Write, 2 Updates, 3 Read-only, 4 Video back | Read/write Mode, Check for updates, Set Read-only Mode, Return to video |
| Finish – resume video (on the Updates step, when the display was already in Read/write Mode) | Cancel |
| Finish – resume video (Everything is up to date, and the last step) | Done |
| Enable Read-Only Mode | Set Read-only Mode |
| Go Live and restart | Go live and restart |
| Skip updates – Enable Read-Only Mode | Skip updates & set Read-only Mode |
| Check For Updates, Finish – resume video (last step) | Check for updates, Done |
| Update All (N) | Update all (N) |

## Icon source

- Icons are [Lucide](https://lucide.dev) SVGs (ISC license), bundled in `src/icons/` with Lucide's license.
- Every icon comes from `lucide-static` 1.80.0, except `github`. Lucide has since removed its brand icons, so that
  one comes from `lucide-static` 1.0.0, the last release that included it. It is the same style and license.
- About credits Lucide under "Made with".
- To add an icon:
  1. Add its meaning to this document.
  2. Add the SVG, at a pinned version, to `src/icons/`.
  3. Add it to the icon table in code.
