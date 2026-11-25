#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Staff Display Tools: one branded window with the everyday display controls (GTK 3).

Open it with the mouse: double-click the video, then click the Staff Tools icon on the taskbar
(also on the desktop and in the app menu). Every staff button does one safe thing. Update
Software and the Setup Mode window (staff_admin.py) are admin windows: anyone can open them, but every
system change asks for the administrator password. Closes itself after 10 minutes without use,
so it never stays on the public screen (not while an admin window is open).

Options: --update opens Update Software (used by the player while an update holds the video),
--setup opens the Setup & Burn-in window, --settings opens Settings.

Look: matches the dark appearance of the LOTTO and FEED apps (Tailwind v4 tokens):
deep navy background with soft radial glows, 20px rounded cards with a gradient fill,
sky-700 borders and sky-400 glow, uppercase letter-spaced labels, pill buttons.

Click feedback: over Pi Connect, actions can take several seconds to show. Every button turns
yellow and says what it's doing the moment it's clicked, a message line explains the wait,
and repeat clicks are ignored until the action finishes, so nothing opens twice.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Gdk, Pango  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import staff_admin  # noqa: E402
import staff_help  # noqa: E402
import ui_icons  # noqa: E402
import ui_screen  # noqa: E402
import loop_profile  # noqa: E402
import loop_state  # noqa: E402

HOME = os.path.expanduser("~")
DATA = loop_profile.data_mount()
STATE = os.path.join(DATA, "state")
STATUS = os.path.join(STATE, "status.json")
IDLE_FLAG = os.path.join(STATE, "idle-override")
VIDEOS = os.path.join(DATA, "videos")
AUTO_CLOSE_S = 10 * 60
APP_TITLE = "Staff Display Tools"
SOURCE_URL = "https://github.com/MattGeiger/LOOP"  # LOOP's own repository (About > Source Code on GitHub)

# LOTTO/FEED dark tokens (Tailwind v4 OKLCH values, as sRGB hex for GTK)
CSS = b"""
* { font-family: "Inter", "Nunito Sans", "DejaVu Sans", sans-serif; }
window.staff, window.report {
  background-color: @bg_start@;
  background-image:
    radial-gradient(ellipse farthest-corner at 16% 86%, alpha(@glow1@, 0.20), transparent 62%),
    radial-gradient(ellipse farthest-corner at 78% 14%, alpha(@glow2@, 0.14), transparent 54%),
    linear-gradient(170deg, @bg_start@, @bg_mid@, @bg_end@);
  color: @text@;
}
label.heading { font-size: 22pt; font-weight: 700; color: @text@; }
label.eyebrow { font-size: 11pt; font-weight: 600; letter-spacing: 3px; color: @text_muted@; }
label.now { font-size: 15pt; font-weight: 600; color: @text@; }
label.next { font-size: 12pt; color: @link@; }
label.warn { font-size: 12pt; font-weight: 700; color: @accent@; }
label.message { font-size: 13pt; font-weight: 700; color: @accent@; }
label.hint { font-size: 11pt; color: @text_muted@; }
box.rule { background-color: @accent@; border-radius: 3px; min-height: 5px; min-width: 96px; }

button.card {
  background-color: transparent;
  background-image: linear-gradient(to top, @card_bottom@, @surface@);
  border: 1px solid alpha(@border@, 0.85);
  border-radius: 20px;
  box-shadow: 1px 3px 10px 0 alpha(@link@, 0.25), 1px 1px 2px 0 alpha(@link@, 0.25);
  padding: 12px 18px;
  color: @text@;
  text-shadow: none;
  -gtk-icon-shadow: none;
}
button.card:hover {
  background-image: linear-gradient(to top, @card_hover_bottom@, @card_hover_top@);
  border-color: @border_hover@;
  box-shadow: 1px 3px 16px 1px alpha(@link@, 0.40), 1px 2px 4px 0 alpha(@link@, 0.30);
}
button.card label.title { font-size: 16pt; font-weight: 700; color: @text@; }
button.card label.sub { font-size: 11pt; color: @text_muted@; }
button.card.busy, button.card.busy:hover {
  background-image: linear-gradient(to top, @accent_deep@, @accent@);
  border-color: @accent_deep@;
  box-shadow: 1px 3px 16px 1px alpha(@accent@, 0.45);
}
button.card.busy label.title, button.card.busy label.sub { color: @on_accent@; }
button.card.confirm, button.card.confirm:hover {
  border: 2px solid @accent@;
  box-shadow: 1px 3px 16px 1px alpha(@accent@, 0.35);
}
button.card.confirm label.title { color: @accent@; }

button.pill {
  background-color: transparent;
  background-image: linear-gradient(to top, @accent_deep@, @accent@);
  border: none;
  border-radius: 999px;
  padding: 10px 26px;
  box-shadow: 1px 3px 12px 0 alpha(@accent@, 0.35);
  text-shadow: none;
}
button.pill label { font-size: 13pt; font-weight: 700; color: @on_accent@; }
button.pill:hover { box-shadow: 1px 3px 18px 2px alpha(@accent@, 0.50); }
button.pill.ghost {
  background-image: linear-gradient(to top, @card_bottom@, @surface@);
  border: 1px solid alpha(@border@, 0.85);
  box-shadow: 1px 3px 10px 0 alpha(@link@, 0.25);
}
button.pill.ghost label { color: @text@; }
button.pill:disabled { opacity: 0.45; }

box.panel {
  background-image: linear-gradient(to top, @card_bottom@, @surface@);
  border: 1px solid alpha(@border@, 0.85);
  border-radius: 20px;
  box-shadow: 1px 3px 10px 0 alpha(@link@, 0.25);
  padding: 14px 18px;
}
label.panel-text { font-family: "DejaVu Sans Mono", monospace; font-size: 11pt; color: @text_body@; }
label.step-title { font-size: 17pt; color: @text@; }
label.step-body { font-size: 11.5pt; color: @text_soft@; }

box.about-card {
  background-image: linear-gradient(to top, @card_bottom@, @surface@);
  border: 1px solid alpha(@border@, 0.85);
  border-radius: 20px;
  box-shadow: 1px 3px 10px 0 alpha(@link@, 0.25);
  padding: 8px 40px 32px 40px;
}
label.about-name { font-size: 24pt; color: @text@; letter-spacing: -0.5px; }
label.about-tag { font-size: 11pt; color: @text_muted@; }
label.about-text { font-size: 11pt; color: @text_muted@; }
label.about-term { font-size: 11pt; color: @text@; }
label.about-small { font-size: 11pt; color: @text_muted@; }
button.about-link, button.about-x { background: none; border: none; box-shadow: none; padding: 2px 0; }
label.about-link { font-size: 11pt; color: @text@; }
button.about-link:hover label.about-link { color: @link@; }
label.about-x { font-size: 13pt; color: @text_muted@; }
button.about-x:hover label.about-x { color: @text@; }

textview.report-text, textview.report-text text {
  background-color: @surface@;
  color: @text_body@;
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 11pt;
}
scrolledwindow.report-scroll {
  border: 1px solid alpha(@border@, 0.85);
  border-radius: 20px;
  background-color: @surface@;
  padding: 10px;
}
button.about-link, button.about-x { min-height: 24px; min-width: 24px; }  /* WCAG 2.2 target size */
button.version-link { background: none; border: none; box-shadow: none; padding: 0 2px; min-height: 24px; min-width: 24px; }
label.version-link { font-size: 11pt; color: @text_muted@; }
button.version-link:hover label.version-link { color: @link@; text-decoration-line: underline; }
window.staff scrolledwindow:not(.report-scroll), window.staff viewport, window.report scrolledwindow:not(.report-scroll) { background-color: transparent; border: none; }
window.staff viewport { background-color: transparent; }
""" + ui_icons.ICON_CSS


def read_status():
    try:
        with open(STATUS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:
        return f"({e})"


def is_running(name):
    return subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0


def launch(cmd):
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def vlc_fullscreen():
    """Put the video back in fullscreen (VLC's local-only interface; password from vlcrc)."""
    import base64
    import urllib.request
    pw = ""
    try:
        with open(os.path.join(HOME, ".config", "vlc", "vlcrc")) as f:
            for line in f:
                if line.startswith("http-password="):
                    pw = line.split("=", 1)[1].strip()
    except OSError:
        return

    def call(query=""):
        req = urllib.request.Request("http://127.0.0.1:8080/requests/status.json" + query)
        req.add_header("Authorization", "Basic " + base64.b64encode(f":{pw}".encode()).decode())
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.load(r)

    try:
        if call().get("fullscreen") in (False, 0, "false"):
            call("?command=fullscreen")
    except Exception:
        pass


def bold(text, weight="bold"):
    # The desktop theme overrides CSS font-weight, so bold comes from Pango markup instead.
    return f'<span weight="{weight}">{GLib.markup_escape_text(text)}</span>'


def label(text, cls, xalign=0.0, wrap=False, weight=None):
    lb = Gtk.Label(xalign=xalign)
    if weight:
        lb.set_markup(bold(text, weight))
    else:
        lb.set_text(text)
    lb.get_style_context().add_class(cls)
    if wrap:
        lb.set_line_wrap(True)
    return lb


def set_app_identity(name):
    """Name the program after its menu entry (the taskbar finds the icon by it) and give its windows LOOP's icon."""
    GLib.set_prgname(name)
    icon = "/var/lib/loop/staff-icon.png" if os.path.isfile("/var/lib/loop/staff-icon.png") else \
        loop_profile.asset("staff-icon.png")
    if icon:
        try:
            Gtk.Window.set_default_icon_from_file(icon)
        except GLib.Error:
            pass


def version_link(window, on_click):
    """'Version x.y.z' under a window's heading, opening the release notes (as in LOTTO and FEED)."""
    b = Gtk.Button()
    b.get_style_context().add_class("version-link")
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.set_halign(Gtk.Align.END)
    b.add(ui_icons.IconLabel(f"Version {APP_VERSION}", "version-link", icon=ui_icons.ICONS["Version"]))
    b.set_tooltip_text("Release notes: what's new in this version")
    b.connect("clicked", lambda *_: on_click())
    return b


class Card(Gtk.Button):
    """A rounded gradient card button with a title and a one-line description."""

    def __init__(self, title, sub, on_click):
        super().__init__()
        self.get_style_context().add_class("card")
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.title_text, self.sub_text = title, sub
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.head = ui_icons.IconLabel(title, size="card", markup=bold(title))
        self.head.set_halign(Gtk.Align.START)
        self.title = self.head.label
        self.title.get_style_context().add_class("title")
        self.title.set_xalign(0.0)
        self.sub = label(sub, "sub", wrap=True)
        self.sub.set_max_width_chars(30)  # wraps inside the card instead of widening the window
        box.pack_start(self.head, False, False, 0)
        box.pack_start(self.sub, False, False, 0)
        self.add(box)
        self.busy = False
        self.connect("clicked", lambda *_: on_click(self))

    def set_text(self, title, sub=None):
        self.title.set_markup(bold(title))
        if sub is not None:
            self.sub.set_text(sub)

    def set_icon_for(self, title):
        """Show the icon of another action (Show idle screen <-> Resume video)."""
        name = ui_icons.icon_for(title)
        if name and self.head.icon is not None and self.head.icon.name != name:
            self.head.icon.name, self.head.icon._rgb = name, None
            self.head.icon.redraw()


class StaffTools(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_TITLE)
        self.get_style_context().add_class("staff")
        self.set_default_size(ui_screen.px(1200), -1)  # designed for 1280x720 (ui_screen); height follows the content
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.connect("destroy", Gtk.main_quit)
        self.last_touch = time.monotonic()
        self.msg_clear_at = None
        self.confirm_until = 0
        self.connect("button-press-event", self.touch)
        self.connect("key-press-event", self.touch)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(14)
        outer.set_margin_bottom(14)
        outer.set_margin_start(32)
        outer.set_margin_end(32)
        self.add(outer)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        logo = loop_profile.asset("logo-white.png")
        if logo:
            head.pack_start(ui_screen.image(logo, 60), False, False, 0)
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title.set_valign(Gtk.Align.CENTER)
        title.pack_start(label(APP_TITLE, "heading", xalign=1.0, weight="bold"), False, False, 0)
        title.pack_start(version_link(self, lambda: self.open_release_notes()), False, False, 0)
        head.pack_end(title, False, False, 0)
        outer.pack_start(head, False, False, 0)
        rule = Gtk.Box()
        rule.get_style_context().add_class("rule")
        rule.set_halign(Gtk.Align.START)
        rule.set_margin_top(8)
        outer.pack_start(rule, False, False, 0)

        # The middle part (the only part that scrolls, on a screen smaller than 720p); the button row stays.
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.pack_start(middle, False, False, 0)
        self.fit_body = middle

        # Setup Mode banner (burn-in testing before go-live); hidden in Production Mode.
        self.banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.banner.get_style_context().add_class("banner")
        self.banner.set_margin_top(10)
        btext = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        btext.pack_start(label("SETUP MODE", "setup-tag", weight="bold"), False, False, 0)
        self.banner_text = label("", "hint", wrap=True)
        self.banner_text.set_lines(2)
        self.banner_text.set_max_width_chars(60)
        self.banner_text.set_ellipsize(Pango.EllipsizeMode.END)
        btext.pack_start(self.banner_text, False, False, 0)
        self.banner.pack_start(btext, True, True, 0)
        setup_btn = self.pill("Setup & Burn-in", lambda *_: self.open_admin("setup"), ghost=True)
        setup_btn.set_valign(Gtk.Align.CENTER)
        self.banner.pack_end(setup_btn, False, False, 0)
        middle.pack_start(self.banner, False, False, 0)

        middle.pack_start(self._spacer(10), False, False, 0)
        middle.pack_start(label("NOW SHOWING", "eyebrow", weight="semibold"), False, False, 0)
        self.now = label("", "now")
        self.next = label("", "next")
        for w in (self.now, self.next):  # one line each; hover shows a long name in full
            w.set_ellipsize(Pango.EllipsizeMode.END)
            w.connect("notify::label", lambda lb, _p: lb.set_tooltip_text(lb.get_text() or None))
        self.warn = label("", "warn", wrap=True)
        for w in (self.now, self.next, self.warn):
            w.set_margin_top(3)
            middle.pack_start(w, False, False, 0)
        middle.pack_start(self._spacer(10), False, False, 0)

        grid = Gtk.Grid(column_spacing=14, row_spacing=14, column_homogeneous=True)
        cards = [
            ("Get a new video", f"Opens {loop_profile.get('content.library_name')} in a private window. "
                                "Downloads play after the current loop.", self.get_video),
            ("Open videos folder", "See or remove the videos on this display.", self.open_folder),
            ("Show idle screen", "Pause the video and show the idle screen.", self.toggle_idle),
            ("Restart video", "Use if the screen looks stuck.", self.restart),
            ("Display status", "What's playing, storage, temperature.", self.show_status),
            ("Performance history", "Last 24 hours: dropped frames, temperature, memory.", self.show_report),
        ]
        self.idle_card = None
        for i, (t, s, fn) in enumerate(cards):
            c = Card(t, s, fn)
            grid.attach(c, i % 3, i // 3, 1, 1)  # 3 across x 2 rows fits 720p
            if fn == self.toggle_idle:
                self.idle_card = c
        middle.pack_start(grid, False, False, 0)

        self.msg = label("", "message", wrap=True)
        self.msg.set_margin_top(10)
        middle.pack_start(self.msg, False, False, 0)

        foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        foot.set_margin_top(10)
        hints = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hints.pack_start(label("To open: double-click the video, then click the Staff Tools icon (top left).",
                               "hint"), False, False, 0)
        links = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)  # second line: hint, Help, About
        links.pack_start(label("Closes by itself after 10 minutes.", "hint"), False, False, 0)
        for text, fn in (("Help", self.open_help), ("About", self.open_about),
                         ("Settings", lambda: self.open_admin("settings"))):
            link = Gtk.Button()
            link.get_style_context().add_class("about-link")
            link.set_relief(Gtk.ReliefStyle.NONE)
            link.add(ui_icons.IconLabel(text, "about-link", markup=bold(text, "semibold")))
            link.connect("clicked", lambda *_, fn=fn: fn())
            links.pack_start(link, False, False, 0)
        hints.pack_start(links, False, False, 0)
        foot.pack_start(hints, False, False, 0)
        self.done_btn = Gtk.Button()
        self.done_btn.get_style_context().add_class("pill")
        self.done_btn.add(ui_icons.IconLabel("Start fullscreen playback", markup=bold("Start fullscreen playback")))
        self.done_btn.connect("clicked", lambda *_: self.done())
        foot.pack_end(self.done_btn, False, False, 0)
        self.admin = {}  # kind -> open admin window
        self.about_win = None
        self.help_win = None
        update_btn = self.pill("Update Software", lambda *_: self.open_admin("update"), ghost=True)
        update_btn.set_margin_end(12)
        update_btn.set_valign(Gtk.Align.END)
        self.done_btn.set_valign(Gtk.Align.END)
        foot.pack_end(update_btn, False, False, 0)
        outer.pack_end(foot, False, False, 0)

        self.refresh()
        GLib.timeout_add_seconds(3, self.refresh)
        GLib.timeout_add_seconds(5, self.tick)

    @staticmethod
    def pill(text, on_click, ghost=False):
        b = Gtk.Button()
        b.get_style_context().add_class("pill")
        if ghost:
            b.get_style_context().add_class("ghost")
        b.add(ui_icons.IconLabel(text, markup=bold(text)))
        b.connect("clicked", on_click)
        return b

    @staticmethod
    def _spacer(h):
        b = Gtk.Box()
        b.set_size_request(-1, h)
        return b

    # --- feedback helpers
    def pump(self):
        while Gtk.events_pending():  # paint the new state before slow work starts
            Gtk.main_iteration_do(False)

    def say(self, text, keep=False):
        self.msg.set_markup(bold(text) if text else "")
        self.msg_clear_at = None if keep or not text else time.monotonic() + 15

    def set_busy(self, card, title, message):
        card.busy = True
        card.get_style_context().add_class("busy")
        card.head.set_busy(True)
        card.set_text(title)
        self.say(message, keep=True)
        win = card.get_window()
        if win:
            win.set_cursor(Gdk.Cursor.new_from_name(card.get_display(), "wait"))
        self.pump()

    def clear_busy(self, card, message=""):
        card.busy = False
        card.get_style_context().remove_class("busy")
        card.head.set_busy(False)
        card.set_text(card.title_text)
        win = card.get_window()
        if win:
            win.set_cursor(None)
        self.say(message)
        self.update_idle_card()

    def guard(self, card):
        if card.busy:
            self.say("Still working on that. One moment, please.")
            return False
        return True

    def wait_until(self, card, check, timeout, done_msg, late_msg, settle=0.0):
        started = time.monotonic()

        def poll():
            try:
                ok = check()
            except Exception:
                ok = False
            elapsed = time.monotonic() - started
            if ok and elapsed >= settle:
                self.clear_busy(card, done_msg)
                return False
            if elapsed > timeout:
                self.clear_busy(card, late_msg)
                return False
            return True

        GLib.timeout_add(500, poll)

    def in_background(self, work, then):
        def worker():
            out = work()
            GLib.idle_add(lambda: (then(out), False)[1])
        threading.Thread(target=worker, daemon=True).start()

    # --- housekeeping
    def touch(self, *_):
        self.last_touch = time.monotonic()
        return False

    def tick(self):
        if self.msg_clear_at and time.monotonic() > self.msg_clear_at:
            self.msg.set_text("")
            self.msg_clear_at = None
        if self.confirm_until and time.monotonic() > self.confirm_until:
            self.cancel_confirm()
        if self.admin or self.help_win is not None:
            self.last_touch = time.monotonic()  # never auto-close while an admin or Help window is open
        if time.monotonic() - self.last_touch > AUTO_CLOSE_S:
            self.done()
            return False
        return True

    def open_admin(self, kind):
        self.touch()
        if kind in self.admin:
            self.admin[kind].present()
            return
        self.say("Opening…")
        self.pump()
        win = staff_admin.open_window(self, kind)
        self.admin[kind] = win
        win.connect("destroy", lambda *_: (self.admin.pop(kind, None), self.refresh()))
        self.say("")

    def open_help(self):
        self.touch()
        if self.help_win is not None:
            self.help_win.present()
            return
        self.help_win = staff_help.HelpWindow(self)
        self.help_win.connect("destroy", lambda *_: setattr(self, "help_win", None))

    def open_release_notes(self):
        self.touch()
        if getattr(self, "notes_win", None) is not None:
            self.notes_win.present()
            return
        self.notes_win = staff_help.ReleaseNotesWindow(self)
        self.notes_win.connect("destroy", lambda *_: setattr(self, "notes_win", None))

    def open_about(self):
        self.touch()
        if self.about_win is not None:
            self.about_win.present()
            return
        self.about_win = AboutWindow(self)
        self.about_win.connect("destroy", lambda *_: setattr(self, "about_win", None))

    def done(self):
        if any(w.busy for w in self.admin.values()):
            self.say("An update or setup step is still running. Wait for it to finish first.")
            return
        self.done_btn.get_child().set_markup(bold("Starting fullscreen playback…"))
        self.done_btn.get_child().set_busy(True)
        self.done_btn.set_sensitive(False)
        self.pump()
        vlc_fullscreen()
        self.destroy()

    def update_idle_card(self):
        c = self.idle_card
        if c and not c.busy and not self.confirm_until:
            if os.path.exists(IDLE_FLAG):
                c.title_text = "Resume video"
                c.set_text("Resume video", "Stop the idle screen and bring the video back.")
                c.set_icon_for("Resume video")
            else:
                c.title_text = "Show idle screen"
                c.set_text("Show idle screen", "Pause the video and show the idle screen.")
                c.set_icon_for("Show idle screen")

    def set_now(self, text):
        self.now.set_markup(bold(text, "semibold"))

    def refresh(self):
        st = read_status()
        idle = os.path.exists(IDLE_FLAG)
        if not st:
            self.set_now("Player status not available yet.")
            self.next.set_text("")
        elif idle:
            self.set_now("The idle screen (video paused)")
            self.next.set_text("Press Resume video to bring the video back.")
        else:
            src = {"backup": "  ·  backup copy (no videos in the folder)"}
            name = "The idle screen" if str(st.get("source", "")).startswith("idle") else (st.get("playing") or "nothing")
            paused = "  ·  paused while this window is open" if st.get("paused_for_staff") else ""
            self.set_now(name + src.get(st.get("source"), "") + paused)
            q = st.get("queued")
            self.next.set_text(f"Up next: {q}  ·  starts after the current loop" if q else "")
        warnings = []
        if not st.get("usb_mounted", True):
            warnings.append("Warning: the USB video drive is not connected.")
        if st.get("usb_mounted", True) and not loop_state.data_kept():
            warnings.append("Warning: Read-only Mode is also covering the USB drive, so new videos and history are "
                            "lost at restart. Turn Read-only Mode off and on again with Update Software.")
        warnings += self.maint_warnings()
        self.warn.set_text("\n".join(warnings))
        self.refresh_banner()
        for w in (self.next, self.warn):
            w.set_visible(bool(w.get_text()))
        self.update_idle_card()
        return True

    def maint_warnings(self):
        try:
            d = loop_state.maint()
        except Exception:
            return []
        stage = d.get("stage")
        if not stage:
            return []
        if d.get("resume_without_ro"):
            return ["Read-only Mode is OFF and the video is running unprotected. "
                    "Click Update Software and Set Read-only Mode."]
        if stage in ("ro_off_pending", "installed", "ro_on_pending"):
            return ["A software update is waiting for a restart. Click Update Software to continue."]
        return ["Software update in progress: the video is paused. Click Update Software to continue."]

    def refresh_banner(self):
        try:
            setup = loop_state.mode() == "setup"
        except Exception:
            setup = False
        self.banner.set_visible(setup)
        if not setup:
            return
        t = loop_state.burnin()["test"]
        state = t.get("state", "idle")
        if state == "running":
            try:
                ends = datetime.fromisoformat(t["ends"])
                left = max(0.0, (ends - datetime.now()).total_seconds() / 3600)
                text = f"Burn-in test running: {t['settings']['hours']} h test, about {left:.1f} h left."
            except (KeyError, ValueError):
                text = "Burn-in test running."
        elif state == "pending_restart":
            text = "Burn-in test starts after the next restart."
        elif state == "finished":
            text = f"Last burn-in test: {t.get('verdict', '?')}. Open Setup & Burn-in to go live."
        elif state in ("stopped", "aborted"):
            text = f"Burn-in test {state}: {t.get('reason', '')}"
        else:
            text = "No burn-in test yet. This display is being set up and is not in service mode."
        self.banner_text.set_text(text)

    # --- actions
    def get_video(self, card):
        if not self.guard(card):
            return
        url = loop_profile.get("content.library_url")
        if not url:
            self.say("No video library is set up for this display yet. Add its link in Settings.")
            return
        if is_running("chromium"):
            self.say("The browser is already open. Look for its window (it may be behind this one).")
            return
        self.set_busy(card, "Opening the library…", "Starting the browser. This can take 10 to 20 seconds…")
        launch(["chromium", url])
        self.wait_until(card, lambda: is_running("chromium"), timeout=45, settle=4,
                        done_msg="Browser opened. Sign in, open the video, then click Download.",
                        late_msg="The browser is slow to start. Wait a moment before trying again.")

    def open_folder(self, card):
        if not self.guard(card):
            return
        self.set_busy(card, "Opening folder…", "Opening the videos folder…")
        launch(["pcmanfm", VIDEOS])
        # The folder opens inside the already-running file manager, so there is nothing to
        # watch for; hold the button for a few seconds so it can't be opened twice.
        self.wait_until(card, lambda: True, timeout=10, settle=6,
                        done_msg="The videos folder is open.", late_msg="")

    def toggle_idle(self, card):
        if not self.guard(card):
            return
        target = not os.path.exists(IDLE_FLAG)
        try:
            if target:
                open(IDLE_FLAG, "w").close()
            else:
                os.remove(IDLE_FLAG)
        except OSError as e:
            self.say(f"Couldn't change the idle screen: {e}")
            return
        if target:
            self.set_busy(card, "Switching…", "Switching to the idle screen (about 5 seconds)…")
            check, done = (lambda: read_status().get("source") == "idle",
                           "The idle screen is showing. Click Resume video to bring the video back.")
        else:
            self.set_busy(card, "Resuming…", "Bringing the video back (about 5 seconds)…")
            check, done = (lambda: read_status().get("source") not in ("idle", None), "The video is playing again.")
        self.wait_until(card, check, timeout=30, done_msg=done,
                        late_msg="This is taking longer than usual. Check the screen in a moment.")

    def restart(self, card):
        if not self.guard(card):
            return
        if not self.confirm_until:  # first click: ask for a second click (no pop-up to get lost)
            self.confirm_card = card
            self.confirm_until = time.monotonic() + 6
            card.get_style_context().add_class("confirm")
            card.set_text("Click again to restart", "The screen goes dark for a few seconds.")
            self.say("Click Restart video again within 6 seconds to confirm.")
            return
        self.cancel_confirm()
        before = read_status().get("playing_since")
        self.set_busy(card, "Restarting…", "Restarting the player. The screen goes dark for a few seconds…")
        launch(["systemctl", "--user", "restart", loop_profile.player_service()])
        self.wait_until(card, lambda: read_status().get("playing_since") not in (None, before), timeout=60,
                        done_msg="The video player restarted.",
                        late_msg="The player is slow to come back. Check Display status in a minute.")

    def cancel_confirm(self):
        c = getattr(self, "confirm_card", None)
        self.confirm_until = 0
        if c:
            c.get_style_context().remove_class("confirm")
            c.set_text(c.title_text, "Use if the screen looks stuck.")

    def show_status(self, card):
        if not self.guard(card):
            return
        self.set_busy(card, "Checking…", "Gathering the display status…")
        self.in_background(status_text, lambda body: (self.clear_busy(card), ReportWindow(self, "Display status", body)))

    def show_report(self, card):
        if not self.guard(card):
            return
        self.set_busy(card, "Loading history…", "Loading the last 24 hours (up to 20 seconds)…")
        work = lambda: run(["python3", os.path.join(loop_profile.CODE_DIR, "burnin_summary.py"), "--hours", "24"])
        self.in_background(work, lambda out: (self.clear_busy(card),
                                              ReportWindow(self, "Performance history (last 24 hours)",
                                                           out or "No data recorded yet.")))


def status_text():
    st = read_status()
    du = shutil.disk_usage(DATA) if os.path.ismount(DATA) else None
    temp = run(["vcgencmd", "measure_temp"]).replace("temp=", "").replace("'C", " °C")
    thr = run(["vcgencmd", "get_throttled"]).replace("throttled=", "")
    ro = run(["findmnt", "-n", "-o", "FSTYPE", "/"])
    stage = loop_state.maint().get("stage")
    lines = [
        f"Display:            {run(['hostname'])}",
        f"Checked:            {datetime.now():%a %b %d, %I:%M %p}",
        "",
        f"Now showing:        {st.get('playing', '?')}",
        f"Source:             {st.get('source', '?')}",
        f"Showing since:      {st.get('playing_since', '?')}",
        f"Up next:            {st.get('queued') or 'nothing queued'}",
        f"Idle screen switch: {'ON (video paused)' if os.path.exists(IDLE_FLAG) else 'off'}",
        "",
        "Videos in folder (newest first):",
        *([f"  - {v}" for v in st.get("videos_in_folder", [])] or ["  (none)"]),
        "",
        f"USB video drive:    {'connected' if du else 'NOT CONNECTED'}"
        + ("" if not du or loop_state.data_kept() else ", NOT KEPT (under Read-only Mode)")
        + (f", {du.free / 1e9:.1f} GB free of {du.total / 1e9:.1f} GB" if du else ""),
        f"Temperature:        {temp}",
        f"Power/heat flags:   {'none' if thr == '0x0' else thr + '  (contact ' + loop_profile.get('identity.contact') + ')'}",
        f"Read-only Mode:     {'ON' if ro == 'overlay' else 'OFF' + ('  (turn back on after maintenance!)' if ro else '')}",
        f"Display mode:       {loop_state.mode().capitalize()}",
        f"Software update:    {stage.replace('_', ' ') if stage else 'none in progress'}",
        f"SSH:                {'on' if loop_state.ssh_enabled() else 'off'}",
    ]
    return "\n".join(lines)


APP_VERSION = "1.1.0"


def about_info():
    """LOOP's credits plus the organization from the profile (nothing organization-specific here)."""
    org = loop_profile.get("identity.organization")
    facts = [("Made by", "Matt Geiger, Temple Consulting, LLC. 2026")]
    if org:
        facts.append(("Made for", org))
    facts += [("Made with", "Raspberry Pi OS, VLC, Python, GTK, Lucide icons, Raspberry Pi Connect, Claude Code, "
                            "and Codex"),
              ("Version", APP_VERSION), ("License", "AGPL-3.0-or-later")]
    notice = "The application code is open source under AGPL-3.0-or-later."
    if loop_profile.get("identity.branding_notice"):
        notice += " " + loop_profile.get("identity.branding_notice")
    return {
        "name": "LOOP",
        "tagline": "Local Outreach on Pi",
        "description": "Outreach videos that play on a loop by themselves, with simple controls for staff, guided "
                       "software updates, burn-in testing and Performance history.",
        "facts": facts,
        "notice": notice,
    }


class AboutWindow(Gtk.Window):
    """Product and credits card, after the About dialogs in LOTTO and FEED: Temple Consulting
    logo, name, tagline and description, a Made by / Made for / Made with list, and a notice."""

    def __init__(self, parent):
        super().__init__(title="About LOOP")
        about = about_info()
        self.get_style_context().add_class("staff")
        self.set_transient_for(parent)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.set_keep_above(True)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class("about-card")
        for side, px in (("top", 22), ("bottom", 22), ("start", 22), ("end", 22)):
            getattr(card, f"set_margin_{side}")(px)
        self.add(card)

        # The window's own title bar closes it; the card has no second close button.

        logo = loop_profile.asset("temple-logo-white.png")
        if logo:
            card.pack_start(ui_screen.image(logo, 72), False, False, 0)
        name = label(about["name"], "about-name", xalign=0.5, weight="semibold")
        name.set_margin_top(18)
        card.pack_start(name, False, False, 0)
        tag = label(about["tagline"], "about-tag", xalign=0.5, weight="medium")
        tag.set_margin_top(4)
        card.pack_start(tag, False, False, 0)
        desc = label(about["description"], "about-text", xalign=0.5, wrap=True)
        desc.set_justify(Gtk.Justification.CENTER)
        desc.set_max_width_chars(52)
        desc.set_margin_top(12)
        card.pack_start(desc, False, False, 0)

        facts = Gtk.Grid(column_spacing=16, row_spacing=8)
        facts.set_halign(Gtk.Align.CENTER)
        facts.set_margin_top(24)
        for row, (k, v) in enumerate(about["facts"]):
            facts.attach(label(k, "about-term", xalign=1.0, weight="medium"), 0, row, 1, 1)
            val = label(v, "about-text", wrap=True)
            val.set_max_width_chars(44)
            facts.attach(val, 1, row, 1, 1)
        card.pack_start(facts, False, False, 0)

        notice = label(about["notice"], "about-small", xalign=0.5, wrap=True)
        notice.set_justify(Gtk.Justification.CENTER)
        notice.set_max_width_chars(60)
        notice.set_margin_top(24)
        card.pack_start(notice, False, False, 0)

        src_btn = Gtk.Button()
        src_btn.get_style_context().add_class("pill")
        src_btn.get_style_context().add_class("ghost")
        src_btn.add(ui_icons.IconLabel("Source Code on GitHub", markup=bold("Source Code on GitHub")))
        src_btn.set_halign(Gtk.Align.CENTER)
        src_btn.set_margin_top(24)
        src_btn.set_tooltip_text(SOURCE_URL)
        src_btn.connect("clicked", lambda *_: self.open_source(parent))
        card.pack_start(src_btn, False, False, 0)
        self.show_all()
        ui_screen.fit(self)


    def open_source(self, parent):
        """LOOP's source code in the browser; this card closes so the browser isn't hidden behind it."""
        launch(["chromium", SOURCE_URL])
        if parent is not None and hasattr(parent, "say"):
            parent.say("Opening LOOP's source code in the browser. It can take 10 to 20 seconds.")
        self.destroy()


class ReportWindow(Gtk.Window):
    def __init__(self, parent, title, body):
        super().__init__(title=title)
        self.get_style_context().add_class("report")
        self.set_transient_for(parent)
        ui_screen.clamp_size(self, 1100, 600)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.set_keep_above(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(24)
        self.add(box)
        box.pack_start(label(title.upper(), "eyebrow", weight="semibold"), False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.get_style_context().add_class("report-scroll")
        tv = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        tv.get_style_context().add_class("report-text")
        tv.get_buffer().set_text(body)
        sw.add(tv)
        box.pack_start(sw, True, True, 0)
        close = Gtk.Button()
        close.get_style_context().add_class("pill")
        close.add(ui_icons.IconLabel("Close", markup=bold("Close")))
        close.set_halign(Gtk.Align.END)
        close.connect("clicked", lambda *_: self.destroy())
        box.pack_end(close, False, False, 0)
        self.show_all()
        ui_screen.scale_tree(self)


def main():
    # Only one Staff Tools window at a time (repeat clicks on the taskbar icon do nothing).
    lock = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "loop-staff-tools.pid")
    try:
        with open(lock) as f:
            os.kill(int(f.read().strip()), 0)
        return  # already open
    except (OSError, ValueError):
        pass
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    set_app_identity("loop-staff-tools")
    provider = Gtk.CssProvider()
    import settings_ui
    provider.load_from_data(ui_screen.scale_css(loop_profile.themed_css(
        CSS + staff_admin.ADMIN_CSS + staff_help.HELP_CSS + settings_ui.SETTINGS_CSS)))
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_USER)
    win = StaffTools()
    win.show_all()
    win.refresh()
    ui_screen.fit(win)  # scale for this screen; only the middle scrolls on a screen smaller than 720p
    if "--update" in sys.argv:
        GLib.idle_add(lambda: (win.open_admin("update"), False)[1])
    elif "--setup" in sys.argv:
        GLib.idle_add(lambda: (win.open_admin("setup"), False)[1])
    elif "--settings" in sys.argv:
        GLib.idle_add(lambda: (win.open_admin("settings"), False)[1])
    Gtk.main()


if __name__ == "__main__":
    main()
