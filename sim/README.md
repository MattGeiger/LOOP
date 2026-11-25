# LOOP test environments

Test LOOP on a development computer before it goes near a real display. Each level catches different problems.
A change that passes all of them is ready for a spare Pi.

| Level | What it runs | Time | Catches |
| --- | --- | --- | --- |
| 1. Unit tests (`tests/`) | Python, no GTK | seconds | Logic: burn-in verdicts, settings, contrast, undo, organization text in code |
| 2. Docker UI test (`sim/docker`) | Real GTK 3.24 on a virtual screen | ~20 s | Layout and wording of every window; makes screenshots |
| 3. **loop-pios VM** (`sim/pios`, UTM on Apple silicon) | The official Raspberry Pi OS image for a Pi 4, with a Debian arm64 kernel | minutes | Package install and removal, services, the password dialog, Update Software, the real raspi-config read-only switch, the USB data drive |
| 4. Spare Pi 4 | Real hardware | hours | Video smoothness, temperature, throttling, Raspberry Pi Connect |

## 2. Docker UI test

```bash
docker build -t loop-ui-test sim/docker
```

```bash
docker run --rm -v "$PWD":/loop loop-ui-test
```

Screenshots land in `sim/out/`, which Git ignores.
- The run uses `profiles/default`; set `LOOP_THEME_PROFILE` to draw another profile.
- It uses made-up display state, and the screenshot script supplies answers a Pi would give (temperature, data
  drive).
- Privileged actions are replaced by a stand-in that succeeds.

**Help screenshots** also come from this harness:
1. Run it with `LOOP_SCREEN=1280x720` and `LOOP_SHOTS=/loop/sim/out/help`.
2. Run `python3 sim/help/make_help_images.py`, which crops each picture and outlines the control its step is about.

`tests/test_help_images.py` lists the pictures that have to be captured on a Pi desktop.

## 3. loop-pios VM (recommended)

This is the official **Raspberry Pi OS (64-bit)** image that Raspberry Pi Imager offers for a Pi 4 (Debian 13
trixie, `cloudinit-rpi`). It runs in UTM with 4 cores and 2 GB. A 4 GB second disk is attached **as a USB drive**,
for LOOP's data drive.

Only the boot path differs from a Pi. A VM has no Pi firmware, so the build:
- copies the image's boot partition and system partition byte for byte;
- adds a small UEFI partition with GRUB and Debian's arm64 kernel.

Everything else is the image as Pi Imager writes it. That includes Imager-style first-boot settings: cloud-init
files on `/boot/firmware` with user `loop`, hostname `loop-pios`, an SSH key and desktop auto-login.

1. Download the image listed in Pi Imager's catalog (`https://downloads.raspberrypi.com/os_list_imagingutility_v4.json`)
   into `sim/pios/work/`. Check its `.sha256`, unpack it to `work/raspios.img`, and check Imager's `extract_sha256`.
2. Run `sim/pios/make-vm.sh`. It builds the disk in a privileged Docker container (`build-image.sh`) and creates
   the **loop-pios** VM in UTM. Start it; first boot takes about a minute. To boot a LOOP image instead:
   `VM_NAME=loop-image SRC_IMG=loop-pios_<version>_arm64.img sim/pios/make-vm.sh`.
3. Run `sim/pios/test-readonly.sh` to check read-only mode end to end with the real `raspi-config`.

Generated files go in `sim/pios/work/`, which Git ignores: disks, the seed, the SSH key and a throwaway test
password.

**UTM notes:**
- Copies of a VM share one network card address, so only one can run at a time. To run more, give each copy a new
  address under **Edit > Network > Random**.
- Use the `virtio-gpu-pci` display card (**Edit > Display**). The accelerated `virtio-gpu-gl-pci` card draws VLC's
  video and Chromium as black.
- Software drawing doesn't scale a 1920x1080 video down to the VM's screen, so judge the picture on a Pi.

**How read-only mode works in the VM.** `raspi-config` edits `/boot/firmware/cmdline.txt` exactly as on a Pi. A
small watcher (`loop-sim-grub.path`) then:
- rebuilds the VM kernel's initramfs;
- writes the GRUB menu from `cmdline.txt` (`loop-sim-grubcfg`, `/etc/grub.d/09_loop_sim`).

So `overlayroot=tmpfs:recurse=0` takes effect at the next restart, as it would on a Pi.

## 3b. loop-sim VM (Debian cloud image, superseded)

An older UTM bench: Debian 13 arm64 with the Raspberry Pi desktop packages added. The packages are
`rpd-wayland-core` (LightDM auto-login, labwc, the Pi taskbar and file manager, polkit agent), VLC, Chromium and
`raspi-config`. Build it with `sim/vm/setup-vm.sh`. The loop-pios VM replaces it.

### What the VMs cannot show

| Pi piece | In the VM | Effect on testing |
| --- | --- | --- |
| VideoCore (`vcgencmd`) | `sim/vm/standins/vcgencmd`: 48.3 °C, no throttling. To test failures, write `/etc/loop-sim/temp_c` or `/etc/loop-sim/throttled` | Temperatures and throttle flags are not real |
| Pi boot firmware | GRUB follows `cmdline.txt`, and the real `raspi-config` switches read-only mode | Only the boot loader differs |
| Hardware video decode | VLC decodes in software | Don't judge smoothness or dropped frames here |
| Raspberry Pi Connect | Installed, but not usable on non-Pi hardware | Test remote access on a real Pi |
| Pi 4 timing and heat | Apple silicon virtualization is much faster | Performance numbers aren't comparable |
