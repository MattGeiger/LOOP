# Agent guide

LOOP (Local Outreach on Pi) turns a Raspberry Pi and a TV into an outreach display that loops an organization's
video by itself.
Read [README.md](README.md) and [docs/ROADMAP.md](docs/ROADMAP.md) first.

## Rules

- This repository is public. Never commit credentials, home-network addresses, device logs, session
  transcripts, browser profiles or production media. Keep documentation to development: no deployment
  narrative or operational data. Deployment notes belong in the organization's own private repository.
- Organization-specific values (names, logos, colors, wording, the video library URL, device names) belong in a
  profile under `profiles/`, never hard-coded in `src/`.
- Keep the display mouse-only: keyboard shortcuts are unreliable over Pi Connect from a Mac. Every control
  shows immediate feedback and ignores repeat clicks while busy.
- Keep both Pi outputs in normal landscape; portrait displays use pre-rotated content.
- Privileged actions go only through the root helper and its polkit action, behind the administrator password.
- Run the tests in `tests/` before committing. Changes that touch a live display are tested on one device first.
- Code is AGPL-3.0-or-later; add the SPDX header used in LOTTO and FEED to new source files.

## Attribution

Matt Geiger, Temple Consulting, LLC. is the creator. Credits in the About window follow LOTTO and FEED.
