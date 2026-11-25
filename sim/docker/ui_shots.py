# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Draw every Staff Display Tools window with real GTK and save screenshots.

Runs inside the loop-ui-test container (sim/docker) on a virtual 1920x1080 display, with the
example profile and made-up display state, so nothing touches a real Pi. Privileged actions are
replaced by a stand-in that "succeeds". Screenshots land in sim/out/ (or $LOOP_SHOTS).

  docker run --rm -v "$PWD":/loop loop-ui-test
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.environ.get("LOOP_SHOTS", os.path.join(ROOT, "sim", "out", os.environ.get("LOOP_THEME_PROFILE", "default")))
os.makedirs(OUT, exist_ok=True)

# Example profile + site, and a throwaway data drive with plausible player state.
CFG = tempfile.mkdtemp()
DATA = tempfile.mkdtemp()
PROFILE = os.environ.get("LOOP_THEME_PROFILE", "default")  # which profile to draw (default or wth)
shutil.copy(os.path.join(ROOT, "profiles", PROFILE, "profile.json"), os.path.join(CFG, "profile.json"))
site = json.load(open(os.path.join(ROOT, "profiles", "default", "site.example.json")))
site["system"]["data_mount"] = DATA
json.dump(site, open(os.path.join(CFG, "site.json"), "w"))
os.environ["LOOP_CONFIG_DIR"] = CFG
os.environ["LOOP_BRANDING_DIR"] = os.path.join(ROOT, "profiles", PROFILE)  # the profile's logos
for d in ("state", "logs", "videos"):
    os.makedirs(os.path.join(DATA, d))
json.dump({"updated": "2026-11-23T10:00:00", "playing": "Winter Coat Drive.mp4", "source": "usb",
           "playing_since": "2026-11-23T08:00:00", "queued": "Holiday Hours.mp4", "usb_mounted": True,
           "idle_override": False, "update_hold": False,
           "videos_in_folder": ["Holiday Hours.mp4", "Winter Coat Drive.mp4"]},
          open(os.path.join(DATA, "state", "status.json"), "w"))
os.environ["XDG_RUNTIME_DIR"] = tempfile.mkdtemp()

sys.path.insert(0, os.path.join(ROOT, "src"))
import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
import loop_profile  # noqa: E402
import loop_state  # noqa: E402
import staff_admin  # noqa: E402
import staff_help  # noqa: E402
import staff_tools  # noqa: E402
import ui_screen  # noqa: E402

# Stand-ins for the Pi: helper present, USB mounted, read-only on, SSH on; root actions succeed.
loop_state.helper_installed = lambda: True
loop_state.usb_ok = lambda: True
loop_state.ro_now = lambda: True
loop_state.ro_next = lambda: True
loop_state.ssh_enabled = lambda: True
staff_admin.helper_busy = lambda: False
staff_admin.run_root = lambda args, on_done, on_line=None, log_path=None: GLib.idle_add(
    lambda: (on_done(0, "ok"), False)[1])

provider = Gtk.CssProvider()
provider.load_from_data(ui_screen.scale_css(loop_profile.themed_css(staff_tools.CSS + staff_admin.ADMIN_CSS + staff_help.HELP_CSS)))
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

shots = []
RECTS = {}  # shot name -> {control: [x, y, w, h]} in window pixels, for the Help screenshots (sim/help)


def rect(win, shot_name, name, widget):
    """Remember where a control is drawn, so Help screenshots can outline it."""
    settle(0.2)
    pos = widget.translate_coordinates(win, 0, 0)
    if pos:
        w = widget.get_allocated_width()
        if isinstance(widget, Gtk.Label):  # the text itself, not the whole row
            w = min(w, widget.get_layout().get_pixel_size()[0] + 4)
        RECTS.setdefault(shot_name, {})[name] = [pos[0], pos[1], w, widget.get_allocated_height()]


def settle(seconds=1.6):
    end = GLib.get_monotonic_time() + int(seconds * 1e6)
    while GLib.get_monotonic_time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def shot(win, name):
    settle()
    gw = win.get_window()
    w, h = gw.get_width(), gw.get_height()
    pb = Gdk.pixbuf_get_from_window(gw, 0, 0, w, h)
    path = os.path.join(OUT, f"{name}.png")
    pb.savev(path, "png", [], [])
    shots.append((name, w, h))


main = staff_tools.StaffTools()
main.show_all()
main.refresh()
ui_screen.fit(main)
shot(main, "main-window")
rect(main, "main-window", "next", main.next)
rect(main, "main-window", "now", main.now)
rect(main, "main-window", "done", main.done_btn)
_m, nat = main.get_child().get_preferred_height_for_width(main.get_allocated_width())
print(f"main window: content {nat}px tall, room {ui_screen.workarea()[1] - ui_screen.TITLE_AND_MARGIN}px, "
      f"scale {ui_screen.scale():g}, middle scrolls: {isinstance(main.fit_body.get_parent(), Gtk.Viewport)}")

def find_card(widget, title):
    if isinstance(widget, staff_tools.Card) and widget.title_text == title:
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = find_card(child, title)
            if found:
                return found
    return None


main.restart(find_card(main, "Restart video"))
shot(main, "restart-confirm")
rect(main, "restart-confirm", "restart", find_card(main, "Restart video"))
main.cancel_confirm()

# A yellow warning (the USB drive unplugged), for Help's troubleshooting guide.
st_path = os.path.join(DATA, "state", "status.json")
st_saved = json.load(open(st_path))
json.dump(dict(st_saved, usb_mounted=False), open(st_path, "w"))
pass  # the warning comes from status.json (usb_mounted)
main.refresh()
shot(main, "help-warning")
rect(main, "help-warning", "warn", main.warn)
rect(main, "help-warning", "now", main.now)
json.dump(st_saved, open(st_path, "w"))
pass
main.refresh()

main.open_about()
shot(main.about_win, "about")
main.about_win.destroy()
main.open_release_notes()
shot(main.notes_win, "release-notes")
main.notes_win.destroy()

main.open_help()
shot(main.help_win, "help")
main.help_win.show_guide(2)
shot(main.help_win, "help-guide")
main.help_win.show_guide(4)  # Updates and Setup: wizard and Settings pictures
shot(main.help_win, "help-guide-setup")
main.help_win.destroy()

# What a healthy Pi reports (the container has no vcgencmd, and its data folder isn't a mount point).
PI_ANSWERS = {("vcgencmd", "measure_temp"): "temp=58.4'C", ("vcgencmd", "get_throttled"): "throttled=0x0",
              ("hostname",): "display-1", ("findmnt", "-n", "-o", "FSTYPE", "/"): "overlay"}
real_run, real_ismount = staff_tools.run, os.path.ismount
staff_tools.run = lambda cmd: PI_ANSWERS.get(tuple(cmd)) or real_run(cmd)
os.path.ismount = lambda p: p.rstrip("/") == DATA.rstrip("/") or real_ismount(p)
loop_state.data_kept = lambda: True
real_du = staff_tools.shutil.disk_usage
staff_tools.shutil.disk_usage = lambda p: real_du(p)._replace(total=30_800_000_000, used=2_400_000_000,
                                                               free=28_400_000_000)
win = staff_tools.ReportWindow(main, "Display status", staff_tools.status_text())
staff_tools.run, os.path.ismount, staff_tools.shutil.disk_usage = real_run, real_ismount, real_du
shot(win, "display-status")
win.destroy()

main.open_admin("update")
upd = main.admin["update"]
shot(upd, "update-software")
upd.found = {"system": (12, "libc6 openssl linux-image-rpi-v8"), "vlc": (2, "vlc vlc-plugin-base"),
             "connect": (0, ""), "chromium": (1, "chromium")}
upd.origin = "ro"
upd.p_choose()
shot(upd, "update-choose")
upd.p_post()
shot(upd, "update-post")
upd.destroy()

loop_state.usb_ok = lambda: False  # no USB data drive: Setup & burn-in sends you to Settings
main.open_admin("setup")
shot(main.admin["setup"], "setup-no-drive")
main.admin["setup"].destroy()
loop_state.usb_ok = lambda: True
main.open_admin("setup")
setup = main.admin["setup"]
shot(setup, "setup-burnin")
# A test whose time is up, and one failing mid-run (no history recorded, so the uptime check fails).
from datetime import datetime as _dt, timedelta as _td
_settings = dict(loop_state.burnin()["settings"])
for _name, _start, _end in (("setup-burnin-finished", -25, -1), ("setup-burnin-failing", -2, 22)):
    loop_state.save_burnin(test={"state": "running", "settings": _settings,
                                 "started": (_dt.now() + _td(hours=_start)).isoformat(timespec="seconds"),
                                 "ends": (_dt.now() + _td(hours=_end)).isoformat(timespec="seconds")})
    setup.show_current()
    shot(setup, _name)
loop_state.save_burnin(test={"state": "idle"})
setup.show_current()
setup.p_golive()
shot(setup, "go-live")
setup.destroy()

# Settings: in Read-only mode it points to Update Software; otherwise every page.
import settings_ui  # noqa: E402
if PROFILE == "default":  # LOOP's own screenshots (and Help) never show an organization's profile
    settings_ui.S.packaged_profiles = lambda: ["default"]
sp = Gtk.CssProvider()
sp.load_from_data(ui_screen.scale_css(loop_profile.themed_css(settings_ui.SETTINGS_CSS)))
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), sp, Gtk.STYLE_PROVIDER_PRIORITY_USER)
settings_ui.usb_drives = lambda: [("/dev/sda", "SanDisk Ultra Fit, 58.4G (/dev/sda)")]
main.open_admin("settings")
st = main.admin["settings"]
shot(st, "settings-readonly")
st.destroy()
loop_state.ro_now = lambda: False
main.open_admin("settings")
st = main.admin["settings"]
for pid, *_ in settings_ui.SETTINGS_PAGES:
    st.switch(pid)
    shot(st, f"settings-{pid}")
    if isinstance(st.fit_body.get_parent(), Gtk.Viewport):
        print(f"settings page {pid} SCROLLS")
st.form = None
st.values["content.library_url"] = "not a link"
st.values["theme.accent"] = "#203060"
st.show_page("colors")
st.busy = True
st.save(st.saved)
shot(st, "settings-errors")
st.destroy()

wiz = settings_ui.SetupWizard()
wiz.disconnect_by_func(Gtk.main_quit)
shot(wiz, "wizard-0-start")
wiz.open_about()
shot(wiz.about_win, "wizard-about")
wiz.about_win.destroy()
wiz.open_help()
shot(wiz.help_win, "wizard-help")
wiz.help_win.destroy()
wiz.start()
# Long values must wrap, never widen the window (a real library link is often 150+ characters).
LONG_URL = ("https://example.sharepoint.com/sites/Development/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2F"
            "Outreach%2FShared%20Documents%2FDisplay%20Videos&viewid=0b6a1c2e-1234-4cde-9f00")
wiz.values["content.library_url"] = LONG_URL
wiz.values["identity.organization"] = "An Organization With A Rather Long Name For Testing How Labels Wrap"
long_pic = os.path.join(CFG, "a-very-long-picture-file-name-for-the-idle-screen-in-portrait-orientation-final-v2.png")
shutil.copy(os.path.join(ROOT, "profiles", "default", "idle-screen-portrait.png"), long_pic)
wiz.files["file.idle_portrait"] = long_pic
widths = {}
for step in range(1, 7):
    wiz.step = step
    wiz.show_step()
    shot(wiz, f"wizard-{step}-{settings_ui.WIZARD_STEPS[step].lower().replace(' ', '-')}")
    if step == 3:  # This display with no USB drive: setup can't go on until one is plugged in
        settings_ui.usb_drives = lambda: []
        wiz.show_step()
        shot(wiz, "wizard-3-no-drive")
        settings_ui.usb_drives = lambda: [("/dev/sda", "SanDisk Ultra Fit, 58.4G (/dev/sda)")]
        wiz.show_step()
    if step == 5:  # Colors: a mid-tone button color and a light highlight get one-click readable shades
        wiz.form.color_entries["theme.accent"].set_text("#2a9d8f")
        wiz.form.color_entries["colors.accent"].set_text("#7accc8")
        settle(0.5)
        shot(wiz, "wizard-5-colors-suggestion")
        wiz.form.apply_suggestion("theme.accent")
        wiz.form.apply_suggestion("colors.accent")
        settle(0.5)
        shot(wiz, "wizard-5-colors-fixed")
    widths[step] = wiz.get_allocated_width()
    if isinstance(wiz.fit_body.get_parent(), Gtk.Viewport):
        print(f"wizard step {step} ({settings_ui.WIZARD_STEPS[step]}) SCROLLS")
wiz.destroy()
want = ui_screen.px(1100)
wide = {k: v for k, v in widths.items() if v > want}
print(f"wizard widths with long values: {sorted(set(widths.values()))} (design {want})"
      + (f" TOO WIDE on steps {sorted(wide)}" if wide else " ok"))

# How tall each wizard page wants to be, unconstrained (design pixels at scale 1).
need = settings_ui.SetupWizard()
need.disconnect_by_func(Gtk.main_quit)
need.fit_max = 99999
need.set_size_request(ui_screen.px(1100), -1)
need.values["content.library_url"] = LONG_URL
heights = {}
for step in range(0, 7):
    need.step = step
    need.show_step()
    settle(0.6)
    heights[settings_ui.WIZARD_STEPS[step]] = need.get_child().get_preferred_height_for_width(ui_screen.px(1100))[1]
need.destroy()
print("wizard page heights:", heights, "tallest", max(heights.values()))
json.dump(RECTS, open(os.path.join(OUT, "rects.json"), "w"), indent=1)
print("\n".join(f"{n}.png  {w}x{h}" for n, w, h in shots))
print(f"{len(shots)} screenshots in {OUT}")
