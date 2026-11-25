# Hardware validation

A checklist for testing a LOOP build on real Raspberry Pi 4s, one installed each way.

| Pi | Route | What you need |
| --- | --- | --- |
| A | **LOOP image → Pi**: write the LOOP image with Raspberry Pi Imager | `loop-pios_<version>_arm64.img.xz` |
| B | **Standard Pi OS → LOOP installer**: write Raspberry Pi OS (64-bit), then install the package | `loop-display_<version>_all.deb` |

Each Pi also needs a USB drive for the videos (setup erases it), a TV and Raspberry Pi Connect.

## Pi A: the LOOP image

1. In Raspberry Pi Imager, set **Choose Device** to Raspberry Pi 4. Under **Choose OS**, pick **Use custom** and the
   LOOP `.img.xz` (or add `dist/loop-imager.json` as a custom repository; see below). Under **Choose Storage**, pick
   the card.
2. Apply OS customisation: hostname, username and password, Wi-Fi if used, SSH, keyboard layout.
3. Boot the Pi with the TV and USB drive connected. Pi OS sets itself up and restarts once.
4. **LOOP Setup** opens at the first login. On **This display**, choose the USB drive and tick the erase box. Save
   with the administrator password.

## Pi B: standard Pi OS plus the installer

1. Write **Raspberry Pi OS (64-bit)** with Pi Imager, using the same customisation. Boot and finish Pi OS setup.
2. Copy the `.deb` to the Pi and install it:
   `sudo apt install ./loop-display_<version>_all.deb`
3. Log out and back in, or open **Preferences > LOOP Setup**, then go through LOOP Setup as for Pi A.

## Check on both

- [ ] LOOP Setup fits the TV, every step works with the mouse only, and saving asks for the password once.
- [ ] After setup, the desktop picture, taskbar icon and desktop icon follow the profile.
- [ ] **Get a new video** opens the library in a private window with no keyring prompt. A download plays after the
      current loop.
- [ ] On the real TV, the video is full screen, sharp and smooth. A sideways TV shows pre-rotated videos upright,
      and the idle screen is turned correctly.
- [ ] Opening Staff Display Tools pauses the video, and **Done** resumes it full screen.
- [ ] Help, Release Notes (click the version), About and Settings open and read well on the TV.
- [ ] **Display status** shows a real temperature. After an hour of video, Performance History shows steady
      temperature and CPU use.
- [ ] Making the idle video during setup takes under about two minutes.
- [ ] After a power cut and restart, the video comes back by itself from the USB drive.
- [ ] With the network unplugged, the video keeps playing.
- [ ] The burn-in test passes in read-only mode (**Setup & burn-in**).
- [ ] After **Finish Setup (Go Live)**, read-only mode is on and Performance History keeps 24 hours.
- [ ] Staff Display Tools works over **Raspberry Pi Connect** screen sharing.
- [ ] After a restart, the taskbar and desktop keep the profile's colors.
- [ ] Removing LOOP (`sudo apt remove loop-display`) restores the desktop. Test this on a spare card.

Don't plug devices into the USB ports while the video plays. A new device in the port beside the data drive can
reset the drive.

## Adding the LOOP image to Pi Imager as a repository

`packaging/build-pi-image.sh` also writes `dist/loop-imager.json`.

1. Serve the `dist` folder:
   `python3 -m http.server 8765 --directory dist`
2. In Pi Imager, open **App Options** > **Content Repository** > **Use custom file** and choose
   `dist/loop-imager.json`.

LOOP then appears under **Choose OS** with its icon, and Pi Imager offers OS customisation for it
(`init_format: cloudinit-rpi`). **Use custom** with the `.img.xz` works without the repository file.
