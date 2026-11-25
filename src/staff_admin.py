#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Admin windows for Staff Display Tools: Update Software, Setup Mode (burn-in test) and Go Live.

Anyone can open these windows and read them; every action that changes the system first asks
for the administrator password in Raspberry Pi OS's own dialog (pkexec + polkit policy
com.templepdx.loop.maintenance, which runs only /usr/libexec/loop/loop-maintenance-root).

The workflow state lives on the USB drive (loop_state), so it survives each restart. After a
restart the player opens Staff Display Tools again on the right step while video is held.
Same look and click rules as the main window: instant feedback, repeat clicks ignored.
"""
import os
import subprocess
import threading
import time
from datetime import datetime

from gi.repository import GLib, Gtk

import burnin_eval
import ui_screen
import loop_state

ADMIN_CSS = b"""
label.step-title { font-size: 17pt; color: @text@; }
label.step-body { font-size: 12pt; color: @text_soft@; }
label.setup-tag { font-size: 11pt; letter-spacing: 3px; color: @accent@; }
label.danger { font-size: 12pt; color: @danger@; }
label.ok { font-size: 12pt; color: @ok@; }
label.count { font-size: 30pt; color: @accent@; }
label.field { font-size: 12pt; color: @text@; }
box.banner {
  background-image: linear-gradient(to right, alpha(@accent@, 0.16), alpha(@accent@, 0.04));
  border: 1px solid alpha(@accent@, 0.55);
  border-radius: 16px;
  padding: 10px 16px;
}
checkbutton label, radiobutton label { color: @text@; font-size: 12pt; }
checkbutton, radiobutton { padding: 4px 0; }
scale mark label, scale value { color: @text_soft@; }
scale trough { min-height: 8px; border-radius: 4px; background-color: @card_bottom@; }
scale highlight { background-color: @link@; border-radius: 4px; }
spinbutton, spinbutton entry { background-color: @surface@; color: @text@; font-size: 12pt; }
progressbar trough { min-height: 12px; border-radius: 6px; background-color: @card_bottom@; }
progressbar progress { min-height: 12px; border-radius: 6px; background-color: @link@; }
button.link-btn { background: none; border: none; box-shadow: none; padding: 4px 6px; }
button.link-btn label { color: @text_muted@; font-size: 11pt; }
button.link-btn.confirm label { color: @danger@; }
button.link-btn { min-height: 24px; min-width: 24px; }  /* WCAG 2.2 target size */
"""

STORAGE_WARNING = ("Always switch back to Read-only Mode before the video resumes. Without it, losing "
                   "power (a pulled plug or an outage) can corrupt the storage card, and the display "
                   "may not start again until it is repaired.")
RW_TEST_WARNING = ("Read/Write mode is not recommended. If the Pi loses power during the test, the storage "
                   "card can be corrupted and the display may not start again until it is repaired. "
                   "The test also won't show how the display behaves as it will run in service.")
GROUPS = [("system", "Raspberry Pi OS & security"), ("vlc", "VLC video player"),
          ("connect", "Raspberry Pi Connect"), ("chromium", "Chromium browser")]
UPDATE_STEPS = ["1  Read/Write", "2  Updates", "3  Read-only", "4  Video back"]
PASSWORD_MSG = {126: "The password window was closed. Nothing was changed.",
                127: "The password was not accepted, or the password window could not open. Nothing was changed."}


def _bold(text, weight="bold"):
    return f'<span weight="{weight}">{GLib.markup_escape_text(text)}</span>'


def _label(text, cls, wrap=True, weight=None, xalign=0.0):
    lb = Gtk.Label(xalign=xalign)
    if weight:
        lb.set_markup(_bold(text, weight))
    else:
        lb.set_text(text)
    lb.get_style_context().add_class(cls)
    lb.set_line_wrap(wrap)
    lb.set_max_width_chars(80)
    return lb


def run_root(args, on_done, on_line=None, log_path=None):
    """Run the root helper through pkexec in the background.

    Output goes to a file (log_path, or a scratch file) and the helper runs in its own session,
    so closing Staff Display Tools can never cut off an install halfway. on_line(text) gets new
    output as it arrives (GTK thread); on_done(returncode, output) at the end.
    Our windows stay above the video, so they drop that while the password dialog may be up.
    """
    tops = [w for w in Gtk.Window.list_toplevels() if w.get_visible()]
    for w in tops:
        w.set_keep_above(False)
    path = log_path or os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "loop-root-helper.out")

    def worker():
        try:
            with open(path, "a") as out_f:
                start = out_f.tell()
                p = subprocess.Popen(["pkexec", loop_state.ROOT_HELPER, *args], stdout=out_f,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     start_new_session=True)
            with open(path) as f:
                f.seek(start)
                while True:
                    rc = p.poll()
                    chunk = f.read()
                    if chunk and on_line:
                        GLib.idle_add(lambda t=chunk: (on_line(t), False)[1])
                    if rc is not None and not chunk:
                        break
                    time.sleep(0.5)
                f.seek(start)
                out = f.read()
        except OSError as e:
            rc, out = 1, f"Could not run the update helper: {e}"
        GLib.idle_add(lambda: (finish(rc, out.rstrip()), False)[1])

    def finish(rc, out):
        for w in tops:
            try:
                w.set_keep_above(True)
            except Exception:
                pass
        on_done(rc, out)

    threading.Thread(target=worker, daemon=True).start()


def helper_busy():
    """True if the root helper is still running (for example an install from a closed window)."""
    return subprocess.run(["pgrep", "-f", loop_state.ROOT_HELPER], capture_output=True).returncode == 0


def problem(rc, out):
    """Plain-language reason a helper call failed."""
    if rc in PASSWORD_MSG:
        return PASSWORD_MSG[rc]
    if rc == 3:
        return "No internet connection. Check the Wi-Fi connection, then try again."
    last = [l for l in out.splitlines() if l.strip()]
    return "That didn't work: " + (last[-1] if last else f"error {rc}")


class AdminWindow(Gtk.Window):
    """Shared frame: heading, step pills, a body that each page replaces, and a button row."""

    def __init__(self, parent, title, eyebrow):
        super().__init__(title=title)
        self.get_style_context().add_class("staff")
        self.set_transient_for(parent)
        self.set_default_size(ui_screen.px(1100), -1)  # designed for 1280x720 (ui_screen)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.busy = False
        self.token = 0
        self.confirm = None
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for side, px in (("top", 18), ("bottom", 18), ("start", 32), ("end", 32)):
            getattr(outer, f"set_margin_{side}")(px)
        self.add(outer)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        head.pack_start(_label(eyebrow, "eyebrow", wrap=False, weight="semibold"), False, False, 0)
        self.title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)  # subclasses may add a line
        self.title_box.pack_start(_label(title, "heading", wrap=False, weight="bold", xalign=1.0), False, False, 0)
        head.pack_end(self.title_box, False, False, 0)
        outer.pack_start(head, False, False, 0)
        rule = Gtk.Box()
        rule.get_style_context().add_class("rule")
        rule.set_halign(Gtk.Align.START)
        rule.set_margin_top(10)
        outer.pack_start(rule, False, False, 0)
        self.steps = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)  # step pills: always in view
        self.steps.set_margin_top(12)
        outer.pack_start(self.steps, False, False, 0)
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)  # scrolls if needed; pills, buttons stay
        outer.pack_start(middle, False, False, 0)
        self.fit_body = middle
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.body.set_margin_top(12)
        middle.pack_start(self.body, False, False, 0)
        self.msg = _label("", "message")
        self.msg.set_margin_top(10)
        middle.pack_start(self.msg, False, False, 0)
        self.foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.foot.set_margin_top(12)
        outer.pack_start(self.foot, False, False, 0)
        self.connect("destroy", lambda *_: setattr(self, "token", -1))
        self.connect("delete-event", self.on_close)

    def on_close(self, *_):
        if self.busy:
            self.say("Please wait until this step finishes before closing.")
            return True  # keep the window
        return False

    # --- building pages
    def page(self, title, text="", steps=None, active=None, warn=None, danger=None, extra=None,
             buttons=(), links=(), msg=""):
        """Replace the window content. buttons: (label, callback, kind, busy_label);
        kind is "primary" or "ghost". links: small text buttons (label, callback)."""
        self.token += 1
        self.busy = False
        self.confirm = None
        for box in (self.steps, self.body, self.foot):
            for c in box.get_children():
                c.destroy()
        for i, name in enumerate(steps or []):
            pill = _label(name, "step", wrap=False)
            if active is not None and i < active:
                pill.get_style_context().add_class("step-done")
            elif i == active:
                pill.get_style_context().add_class("step-active")
            self.steps.pack_start(pill, False, False, 0)
        self.steps.set_visible(bool(steps))
        self.body.pack_start(_label(title, "step-title", weight="bold"), False, False, 0)
        if text:
            self.body.pack_start(_label(text, "step-body"), False, False, 0)
        if warn:
            self.body.pack_start(_label(warn, "warn"), False, False, 0)
        if danger:
            self.body.pack_start(_label(danger, "danger"), False, False, 0)
        if extra is not None:
            self.body.pack_start(extra, False, False, 4)
        linkbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for text_, cb in links:
            b = Gtk.Button()
            b.get_style_context().add_class("link-btn")
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.add(_label(text_, "hint", wrap=False))
            b.connect("clicked", lambda btn, cb=cb: cb(btn))
            linkbox.pack_start(b, False, False, 0)
        self.foot.pack_start(linkbox, False, False, 0)
        for text_, cb, kind, busy_text in reversed(buttons):
            b = Gtk.Button()
            b.get_style_context().add_class("pill")
            if kind == "ghost":
                b.get_style_context().add_class("ghost")
            b.add(Gtk.Label())
            b.get_child().set_markup(_bold(text_))
            b.orig_text = text_
            b.connect("clicked", lambda btn, cb=cb, bt=busy_text: self.press(btn, cb, bt))
            self.foot.pack_end(b, False, False, 0)
        self.show_all()
        self.steps.set_visible(bool(steps))
        self.say(msg)
        ui_screen.fit(self)

    def say(self, text):
        self.msg.set_markup(_bold(text) if text else "")
        self.msg.set_visible(bool(text))

    def pump(self):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)

    def press(self, btn, cb, busy_text):
        if self.busy:
            self.say("Still working on that. One moment, please.")
            return
        self.busy = True
        if busy_text:
            btn.get_child().set_markup(_bold(busy_text))
        for b in self.foot.get_children():
            if b is not btn and isinstance(b, Gtk.Button):
                b.set_sensitive(False)
        self.say(busy_text or "")
        self.pump()
        cb()

    def unbusy(self, message):
        """Back to the current page after a failed action, with a message."""
        self.busy = False
        for b in self.foot.get_children():
            b.set_sensitive(True)
            if hasattr(b, "orig_text"):
                b.get_child().set_markup(_bold(b.orig_text))
        self.say(message)

    def twice(self, btn, first_text, warn_text, then):
        """Link button that needs a second click within 8 seconds (no pop-up to get lost)."""
        if self.confirm is btn:
            self.confirm = None
            then()
            return
        self.confirm = btn
        btn.get_style_context().add_class("confirm")
        btn.get_child().set_text(first_text)
        self.say(warn_text)
        tok = self.token

        def reset():
            if self.token == tok and self.confirm is btn:
                self.show_current()
            return False
        GLib.timeout_add_seconds(8, reset)

    def restart_page(self, title, text, steps=None, active=None, seconds=15, warn=None):
        """Countdown, then restart through the helper (the password is still remembered)."""
        count = _label(f"{seconds}", "count", wrap=False, weight="bold")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        box.pack_start(count, False, False, 0)
        box.pack_start(_label("seconds until the display restarts.\nThis window closes and the "
                              "screen goes dark for about a minute.", "step-body"), False, False, 0)
        self.page(title, text, steps, active, warn=warn, extra=box,
                  buttons=[("Restart now", self.do_restart, "primary", "Restarting…")])
        tok, left = self.token, [seconds]

        def tick():
            if self.token != tok:
                return False
            left[0] -= 1
            count.set_markup(_bold(str(max(left[0], 0))))
            if left[0] <= 0:
                self.busy = True
                self.say("Restarting…")
                self.do_restart()
                return False
            return True
        GLib.timeout_add_seconds(1, tick)

    def do_restart(self):
        self.token += 1  # stop the countdown
        run_root(["reboot"], lambda rc, out: self.unbusy(problem(rc, out)) if rc else None)

    def show_current(self):
        raise NotImplementedError


# ============================================================ Update Software
class UpdateWindow(AdminWindow):
    def __init__(self, parent):
        super().__init__(parent, "Update Software", "SOFTWARE UPDATE")
        self.found = {}
        self.show_current()

    def show_current(self):
        if not loop_state.usb_ok():
            return self.page("The USB data drive is not connected",
                             "The update steps are saved on the USB drive so they survive each restart. "
                             "Reconnect the drive, then open Update Software again.",
                             buttons=[("Close", self.destroy, "ghost", "")])
        if not loop_state.helper_installed():
            return self.page("The update helper is not installed",
                             "Run install_maintenance.sh on this display once (it needs the admin "
                             "password), then try again.", buttons=[("Close", self.destroy, "ghost", "")])
        d = loop_state.maint()
        stage, note = d.get("stage"), d.get("note")
        self.origin = d.get("origin", "ro")
        if stage is None:
            return self.p_intro()
        if stage == "ro_off_pending":
            return self.p_ro_off_pending(note)
        if stage == "ready":
            return self.p_ready(note)
        if stage == "installing":
            if helper_busy():
                return self.page("Updates are still installing",
                                 "An install started earlier is still running. Leave the display on and "
                                 "check again in a few minutes.", UPDATE_STEPS, 1,
                                 buttons=[("Check again", self.show_current, "primary", "Checking…")])
            return self.p_interrupted(during=True)
        if stage == "interrupted":
            return self.p_interrupted()
        if stage == "installed":
            return self.restart_page("Updates are installed", "The display restarts to finish them.",
                                     UPDATE_STEPS, 1)
        if stage == "post_update":
            return self.p_post(note)
        if stage == "ro_on_pending":
            return self.restart_page("Read-only mode is set", "After the restart the display is protected "
                                     "again and the video resumes by itself.", UPDATE_STEPS, 3)
        return self.page(f"Unknown step: {stage}", buttons=[("Close", self.destroy, "ghost", "")])

    def test_note(self):
        t = loop_state.burnin()["test"]
        if t.get("state") in ("running", "pending_restart"):
            return "This also stops the burn-in test that is running (restarts end a test)."
        return None

    # --- step 1: switch to read/write and restart
    def p_intro(self):
        if loop_state.ro_now():
            self.page("Switch out of Read-only Mode",
                      "Updates can only be saved while read-only mode is off. The display will switch to "
                      "Read/Write mode and restart. The video stays off until the updates are finished and "
                      "read-only mode is back on. The idle screen shows instead.\n\n"
                      "Takes about 10 to 30 minutes, including three restarts. You'll need the "
                      "administrator password.",
                      UPDATE_STEPS, 0, warn=self.test_note(),
                      buttons=[("Cancel", self.destroy, "ghost", ""),
                               ("I understand, switch modes and restart", self.do_ro_off, "primary",
                                "Waiting for the password…")])
        else:
            self.page("This display is already in Read/Write mode",
                      "It's in Setup Mode without read-only protection, so updates can be installed "
                      "right away. The video pauses until you finish. You'll need the administrator "
                      "password.", UPDATE_STEPS, 1, warn=self.test_note(),
                      buttons=[("Cancel", self.destroy, "ghost", ""),
                               ("Continue", self.do_start_rw, "primary", "Waiting for the password…")])

    def do_ro_off(self):
        def done(rc, out):
            if rc:
                return self.unbusy(problem(rc, out))
            loop_state.stop_test("Stopped for a software update")
            loop_state.set_maint("ro_off_pending", origin="ro")
            self.restart_page("Read-only mode turns off at the restart",
                              "After the restart, this window opens again to continue.", UPDATE_STEPS, 0)
        run_root(["ro-off"], done)

    def do_start_rw(self):
        def done(rc, out):
            if rc:
                return self.unbusy(problem(rc, out))
            loop_state.stop_test("Stopped for a software update")
            loop_state.set_maint("ready", origin="rw")
            self.show_current()
        run_root(["selftest"], done)

    def p_ro_off_pending(self, note):
        if note:  # restarted, but read-only is still on
            return self.page("Read-only mode is still on", note, UPDATE_STEPS, 0,
                             buttons=[("Cancel update", self.do_cancel, "ghost", "Cancelling…"),
                                      ("Try again", self.do_ro_off, "primary", "Waiting for the password…")])
        self.page("Restart to continue", "Read-only mode turns off after a restart.", UPDATE_STEPS, 0,
                  buttons=[("Cancel update", self.do_cancel, "ghost", "Cancelling…"),
                           ("Restart now", self.do_restart, "primary", "Restarting…")])

    def do_cancel(self):
        def done(rc, out):
            if rc:
                return self.unbusy(problem(rc, out))
            loop_state.end_maint()
            self.page("Update cancelled", "Read-only mode stays on and the video keeps playing.",
                      buttons=[("Close", self.destroy, "primary", "")])
        run_root(["ro-on"], done)

    # --- steps 4-7: proceed, check, choose, install
    def p_ready(self, note=None):
        if self.origin == "rw":
            text = "The video is paused until you finish. Check for updates to continue."
            alt = ("Finish – resume video", self.do_finish_rw, "ghost", "Finishing…")
        else:
            text = ("This display is no longer in read-only mode, so updates can be installed. The video "
                    "stays off until updates are finished and read-only mode is back on.")
            alt = ("Skip updates – Enable Read-Only Mode", self.do_ro_on, "ghost", "Waiting for the password…")
        self.page("Ready to update", text, UPDATE_STEPS, 1, warn=note,
                  buttons=[alt, ("Check for updates", self.do_check, "primary", "Checking for updates…")],
                  links=[("Change settings (Settings window)", lambda btn: self.get_transient_for().open_admin("settings"))]
                  + list(self.escape_links()))

    def escape_links(self):
        if self.origin == "rw":
            return ()
        return [("Resume video without read-only (not recommended)", self.do_escape)]

    def do_escape(self, btn):
        def go():
            d = loop_state.maint()
            loop_state.set_maint(d.get("stage", "post_update"), origin=self.origin, resume_without_ro=True)
            self.page("Video resumed without read-only protection",
                      "The video comes back in a few seconds. Staff Display Tools shows a warning until "
                      "read-only mode is back on. To finish, open Update Software and click Enable "
                      "Read-Only Mode.", danger=STORAGE_WARNING,
                      buttons=[("Close", self.destroy, "primary", "")])
        self.twice(btn, "Click again to resume video without read-only protection", STORAGE_WARNING, go)

    def do_check(self):
        self.found = {}

        def done(rc, out):
            if rc in PASSWORD_MSG:
                return self.unbusy(problem(rc, out))
            if rc:  # e.g. no internet: back to a page with buttons, with the reason
                return self.p_ready(note=problem(rc, out))
            repair = False
            for line in out.splitlines():
                parts = line.split("\t")
                if parts[0] == "REPAIR":
                    repair = True
                elif len(parts) >= 2 and parts[1].isdigit():
                    self.found[parts[0]] = (int(parts[1]), parts[2] if len(parts) > 2 else "")
            if repair:
                return self.p_interrupted()
            self.p_choose()
        run_root(["check"], done)

    def p_choose(self):
        total = sum(n for n, _ in self.found.values())
        if total == 0:
            return self.p_uptodate()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.checks = {}
        for key, name in GROUPS:
            n, pkgs = self.found.get(key, (0, ""))
            cb = Gtk.CheckButton.new_with_label(f"{name}  ·  {n} update{'s' if n != 1 else ''}"
                                                if n else f"{name}  ·  up to date")
            cb.set_sensitive(n > 0)
            box.pack_start(cb, False, False, 0)
            if n:
                self.checks[key] = cb
                shown = " ".join(pkgs.split()[:8]) + (" …" if len(pkgs.split()) > 8 else "")
                hint = _label(shown, "hint")
                hint.set_margin_start(28)
                box.pack_start(hint, False, False, 0)
        self.page(f"{total} update{'s' if total != 1 else ''} available",
                  "Update All is recommended. To install only some, tick them and click Update selected.",
                  UPDATE_STEPS, 1, extra=box,
                  buttons=[("Update selected", self.do_install_selected, "ghost", "Starting…"),
                           (f"Update All ({total})", lambda: self.install(["all"]), "primary", "Starting…")],
                  links=self.escape_links())

    def do_install_selected(self):
        chosen = [k for k, cb in self.checks.items() if cb.get_active()]
        if not chosen:
            return self.unbusy("Tick at least one group first, or click Update All.")
        self.install(chosen)

    def p_uptodate(self):
        if self.origin == "rw":
            buttons = [("Check again", self.do_check, "ghost", "Checking…"),
                       ("Finish – resume video", self.do_finish_rw, "primary", "Finishing…")]
        else:
            buttons = [("Check again", self.do_check, "ghost", "Checking…"),
                       ("Enable Read-Only Mode", self.do_ro_on, "primary", "Waiting for the password…")]
        self.page("Everything is up to date", "No updates are waiting.", UPDATE_STEPS, 2,
                  warn=None if self.origin == "rw" else STORAGE_WARNING, buttons=buttons,
                  links=self.escape_links())

    def log_view(self):
        sw = Gtk.ScrolledWindow()
        sw.get_style_context().add_class("report-scroll")
        sw.set_size_request(-1, 300)
        tv = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        tv.get_style_context().add_class("report-text")
        tv.set_wrap_mode(Gtk.WrapMode.CHAR)
        sw.add(tv)
        buf = tv.get_buffer()
        end = buf.create_mark("end", buf.get_end_iter(), False)
        self.log_path = os.path.join(loop_state.LOGS, f"updates-{datetime.now():%Y-%m-%d-%H%M}.log")

        def add(text):
            buf.insert(buf.get_end_iter(), text)
            tv.scroll_mark_onscreen(end)
        return sw, add

    def install(self, groups):
        loop_state.set_maint("installing", origin=self.origin, groups=groups)
        sw, add = self.log_view()
        self.page("Installing updates…", "Leave the display on. This usually takes 5 to 20 minutes. "
                  "If the power goes out, the next start offers a repair.", UPDATE_STEPS, 1, extra=sw)
        self.busy = True

        def done(rc, out):
            if rc:
                loop_state.set_maint("ready", origin=self.origin,
                                    note="The last install did not finish. " + problem(rc, out))
                return self.page("The updates did not finish", problem(rc, out), UPDATE_STEPS, 1, extra=sw,
                                 buttons=[("Back", self.show_current, "ghost", ""),
                                          ("Repair and try again", self.do_repair, "primary",
                                           "Repairing…")])
            loop_state.set_maint("installed", origin=self.origin, groups=groups)
            self.restart_page("Updates are installed", "The display restarts to finish them. Afterwards "
                              "this window opens again for the last step.", UPDATE_STEPS, 1)
        run_root(["update", *groups], done, on_line=add, log_path=self.log_path)

    def p_interrupted(self, during=False):
        text = ("The display restarted while updates were installing (for example, the power went out). "
                "Click Repair to finish the install safely before doing anything else.")
        if during:
            text = ("An install was in progress. If it isn't running any more, click Repair to finish it "
                    "safely before doing anything else.")
        self.page("The last update was interrupted", text, UPDATE_STEPS, 1,
                  buttons=[("Repair", self.do_repair, "primary", "Repairing…")])

    def do_repair(self):
        sw, add = self.log_view()
        self.page("Repairing…", "Finishing the interrupted install.", UPDATE_STEPS, 1, extra=sw)
        self.busy = True

        def done(rc, out):
            if rc:
                return self.page("The repair did not finish", problem(rc, out), UPDATE_STEPS, 1, extra=sw,
                                 buttons=[("Try again", self.do_repair, "primary", "Repairing…")])
            loop_state.set_maint("ready", origin=self.origin, note="Repair finished.")
            self.busy = True
            self.say("Repair finished. Checking for updates…")
            self.do_check()
        run_root(["repair"], done, on_line=add, log_path=self.log_path)

    # --- steps 9-10: after the update restart
    def p_post(self, note=None):
        if self.origin == "rw":
            return self.page("Updates are finished", "Click Finish to resume the video.", UPDATE_STEPS, 3,
                             warn=note,
                             buttons=[("Check For Updates", self.do_check, "ghost", "Checking for updates…"),
                                      ("Finish – resume video", self.do_finish_rw, "primary", "Finishing…")])
        self.page("Updates are finished",
                  "The display is still in Read/Write mode, so the video stays off. Enable Read-Only Mode "
                  "to protect the display and bring the video back, or check for more updates.",
                  UPDATE_STEPS, 2, warn=note, danger=STORAGE_WARNING,
                  buttons=[("Check For Updates", self.do_check, "ghost", "Checking for updates…"),
                           ("Enable Read-Only Mode", self.do_ro_on, "primary", "Waiting for the password…")],
                  links=self.escape_links())

    def do_ro_on(self):
        def done(rc, out):
            if rc:
                return self.unbusy(problem(rc, out))
            loop_state.set_maint("ro_on_pending", origin=self.origin)
            self.restart_page("Read-only mode is set", "After the restart the display is protected again "
                              "and the video resumes by itself.", UPDATE_STEPS, 3)
        run_root(["ro-on"], done)

    def do_finish_rw(self):
        loop_state.end_maint()
        self.page("Finished", "The video resumes in a few seconds.", UPDATE_STEPS, 3,
                  buttons=[("Close", self.destroy, "primary", "")])


# ============================================================ Setup Mode
class SetupWindow(AdminWindow):
    def __init__(self, parent):
        super().__init__(parent, "Setup & Burn-in", "SETUP MODE")
        self.parent_tools = parent
        self.unlocked = False
        self.ssh_off = None
        self.show_current()
        GLib.timeout_add_seconds(15, self.live)

    # --- status
    def status_box(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("panel")
        self.verdict = _label("Checking the burn-in test…", "now", weight="bold")
        self.bar = Gtk.ProgressBar()
        self.detail = _label("", "panel-text")
        for w in (self.verdict, self.bar, self.detail):
            box.pack_start(w, False, False, 0)
        return box

    def live(self):
        if self.token < 0:
            return False
        if not hasattr(self, "verdict"):
            return True
        tok = self.token

        def work():
            try:
                return burnin_eval.current()
            except Exception as e:
                return {"verdict": "ERROR", "error": str(e), "breaches": {}, "settings": {}}

        def show(r):
            if self.token != tok:
                return False
            v = r.get("verdict")
            words = {"RUNNING": "Burn-in test running · on track", "FAILING": "Burn-in test running · FAILED a check",
                     "PASS": "Burn-in test PASSED", "FAIL": "Burn-in test FAILED",
                     "STOPPED": "Burn-in test stopped", "NO TEST": "No burn-in test yet",
                     "WAITING FOR RESTART": "Burn-in test starts after the restart",
                     "STARTING": "Burn-in test starting…", "NO DATA": "Burn-in test: no data recorded"}
            self.verdict.set_markup(_bold(words.get(v, v)))
            self.bar.set_fraction(r.get("progress", 1.0 if v in ("PASS", "FAIL") else 0.0))
            self.bar.set_visible("started" in r)
            if "error" in r:
                self.detail.set_text(r["error"])
            elif "started" in r:
                self.detail.set_text(burnin_eval.report(r).split("\n", 1)[1])
            else:
                t = loop_state.burnin()["test"]
                self.detail.set_text(t.get("reason", "Set the test below, then click Start burn-in test."))
            return False
        threading.Thread(target=lambda: GLib.idle_add(show, work()), daemon=True).start()
        return True

    # --- settings
    def settings_box(self, s):
        g = Gtk.Grid(column_spacing=18, row_spacing=10)
        row = 0

        def add(text, widget, hint=None):
            nonlocal row
            g.attach(_label(text, "field", wrap=False), 0, row, 1, 1)
            g.attach(widget, 1, row, 1, 1)
            if hint:
                g.attach(_label(hint, "hint", wrap=False), 2, row, 1, 1)
            row += 1

        hours = list(loop_state.TEST_HOURS)
        self.w_hours = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, len(hours) - 1, 1)
        self.w_hours.set_draw_value(False)
        self.w_hours.set_size_request(380, -1)
        for i, h in enumerate(hours):
            self.w_hours.add_mark(i, Gtk.PositionType.BOTTOM, f"{h} h")
        self.w_hours.set_value(hours.index(s["hours"]) if s["hours"] in hours else 1)
        self.w_hours.connect("value-changed", lambda sc: sc.set_value(round(sc.get_value())))
        add("Test length", self.w_hours)

        def spin(lo, hi, step, digits, value):
            sp = Gtk.SpinButton.new_with_range(lo, hi, step)
            sp.set_digits(digits)
            sp.set_value(value)
            sp.set_halign(Gtk.Align.START)
            return sp
        self.w_temp = spin(60, 90, 1, 0, s["max_temp_c"])
        add("Fail if CPU or GPU reaches", self.w_temp, "°C")
        self.w_mem = spin(40, 95, 1, 0, s["max_mem_pct"])
        add("Fail if memory use reaches", self.w_mem, "%")
        self.w_drop = spin(0.0001, 1.0, 0.0001, 4, s["max_drop_pct"])
        add("Fail if dropped frames reach", self.w_drop, "% of all frames")
        self.w_uptime = Gtk.CheckButton.new_with_label("Fail on any restart, power loss or video stop")
        self.w_uptime.set_active(s["require_uptime"])
        add("Uptime", self.w_uptime)
        self.w_ro = Gtk.RadioButton.new_with_label_from_widget(None, "Read-only Mode (recommended)")
        self.w_rw = Gtk.RadioButton.new_with_label_from_widget(self.w_ro, "Read/Write Mode (not recommended)")
        (self.w_ro if s["read_only"] else self.w_rw).set_active(True)
        mode_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        mode_box.pack_start(self.w_ro, False, False, 0)
        mode_box.pack_start(self.w_rw, False, False, 0)
        add("Run the test in", mode_box)
        self.w_rw_warn = _label(RW_TEST_WARNING, "danger")
        g.attach(self.w_rw_warn, 0, row, 3, 1)
        self.w_rw.connect("toggled", lambda *_: self.w_rw_warn.set_visible(self.w_rw.get_active()))
        for w in (self.w_hours, self.w_temp, self.w_mem, self.w_drop, self.w_uptime, self.w_ro, self.w_rw):
            w.set_sensitive(self.unlocked)
        return g

    def collect(self):
        return {"hours": loop_state.TEST_HOURS[int(round(self.w_hours.get_value()))],
                "max_temp_c": float(self.w_temp.get_value()), "max_mem_pct": float(self.w_mem.get_value()),
                "max_drop_pct": round(float(self.w_drop.get_value()), 4),
                "require_uptime": self.w_uptime.get_active(), "read_only": self.w_ro.get_active()}

    def no_drive_page(self):
        """Burn-in history, the test itself and read-only mode all need the USB data drive."""
        self.page("Set up the USB data drive first",
                  "The burn-in test, Performance History and the videos are kept on the USB data drive, so they "
                  "survive read-only mode and every restart. Without it they would be lost at the next restart. "
                  "Plug in a USB drive, then choose it in Settings > This display.",
                  buttons=[("Close", self.destroy, "ghost", ""),
                           ("Open Settings", self.to_settings, "primary", "Opening…")])

    def to_settings(self):
        parent = self.get_transient_for()
        self.destroy()
        if parent is not None and hasattr(parent, "open_admin"):
            parent.open_admin("settings")

    def show_current(self):
        if not loop_state.usb_ok():
            return self.no_drive_page()
        b = loop_state.burnin()
        t = b["test"]
        running = t.get("state") in ("running", "pending_restart")
        try:  # a test whose time is up (passed or failed) no longer holds the settings
            finished = t.get("state") == "running" and datetime.now() >= datetime.fromisoformat(t["ends"])
        except (KeyError, ValueError):
            finished = False
        try:
            r = burnin_eval.current() if running else {}
            failing = running and (r.get("verdict") in ("FAILING", "FAIL") or bool(r.get("breaches")))
        except Exception:
            failing = False
        running = running and not finished
        s = t.get("settings", b["settings"]) if running else b["settings"]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.pack_start(self.status_box(), False, False, 0)
        box.pack_start(self.settings_box(s), False, False, 0)
        if running and failing:  # it can't pass any more: stop it, change the settings, test again
            buttons = [("Close", self.destroy, "ghost", ""),
                       ("Stop and change settings", self.do_stop_and_unlock, "primary", "Stopping…")]
            links = []
        elif running:
            buttons = [("Close", self.destroy, "ghost", "")]
            links = [("Stop the burn-in test", self.do_stop)]
        elif self.unlocked:
            buttons = [("Save settings", self.do_save, "ghost", "Saving…"),
                       ("Start burn-in test" if not finished else "Start another test", self.do_start, "primary",
                        "Starting…")]
            links = []
        else:
            buttons = [("Change settings", self.do_unlock, "ghost", "Waiting for the password…"),
                       ("Start burn-in test" if not finished else "Start another test", self.do_start, "primary",
                        "Waiting for the password…")]
            links = []
        buttons.insert(0, ("Finish Setup (Go Live)…", self.p_golive, "ghost", ""))
        mode = "Read-only" if loop_state.ro_now() else "Read/Write"
        self.page("Burn-in test", f"Setup Mode: the display is being tested before it goes into service. "
                  f"Right now it is in {mode} Mode." + (" Settings are locked while a test runs." if running else ""),
                  extra=box, buttons=buttons, links=links)
        self.w_rw_warn.set_visible(self.w_rw.get_active())
        self.live()

    def do_stop_and_unlock(self):
        loop_state.stop_test("Stopped after a failed check")
        self.do_unlock()

    def do_unlock(self):
        def done(rc, out):
            if rc:
                return self.unbusy(problem(rc, out))
            self.unlocked = True
            self.show_current()
            self.say("Settings unlocked. Click Save settings or Start burn-in test when ready.")
        run_root(["selftest"], done)

    def do_save(self):
        loop_state.save_burnin(settings=self.collect())
        self.show_current()
        self.say("Settings saved.")

    def do_start(self):
        s = self.collect()
        if loop_state.maint_stage():
            return self.unbusy("Finish the software update first (Update Software).")

        def authed(rc, out):
            if rc:
                return self.unbusy(problem(rc, out))
            loop_state.save_burnin(settings=s)
            if s["read_only"] == loop_state.ro_now():
                loop_state.start_test_now(s)
                self.unlocked = False
                self.show_current()
                return self.say(f"Burn-in test started: {s['hours']} hours.")
            action = "ro-on" if s["read_only"] else "ro-off"

            def switched(rc2, out2):
                if rc2:
                    return self.unbusy(problem(rc2, out2))
                loop_state.mark_test_pending(s)
                self.restart_page("The test starts after a restart",
                                  f"The display restarts in {'Read-only' if s['read_only'] else 'Read/Write'} "
                                  f"Mode and the {s['hours']}-hour test starts by itself.",
                                  warn=None if s["read_only"] else RW_TEST_WARNING)
            run_root([action], switched)
        if self.unlocked:
            authed(0, "")  # the password was entered moments ago
        else:
            run_root(["selftest"], authed)

    def do_stop(self, btn):
        def go():
            loop_state.stop_test("Stopped")
            self.show_current()
            self.say("The burn-in test was stopped.")
        self.twice(btn, "Click again to stop the test", "Stopping ends this test. A new test starts from zero.", go)

    # --- Finish Setup (Go Live)
    def p_golive(self):
        passed = burnin_eval.last_pass()
        t = loop_state.burnin()["test"]
        ssh_on = loop_state.ssh_enabled()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        if ssh_on:
            self.w_ssh = Gtk.CheckButton.new_with_label("Turn off SSH (recommended)")
            self.w_ssh.set_active(True if self.ssh_off is None else self.ssh_off)
            ssh_warn = _label("SSH stays on: anyone on the display's network who has the password can sign in to "
                              "this display. Leave it on only if someone still needs remote shell access.", "danger")
            self.w_ssh.connect("toggled", lambda cb: (setattr(self, "ssh_off", cb.get_active()),
                                                      ssh_warn.set_visible(not cb.get_active())))
            box.pack_start(self.w_ssh, False, False, 0)
            box.pack_start(ssh_warn, False, False, 0)
        else:
            self.w_ssh = None
            box.pack_start(_label("SSH is already off.", "ok"), False, False, 0)
        verdict = (_label("The last burn-in test passed.", "ok") if passed else
                   _label("No burn-in test has passed on this display. Going live without a passing test "
                          "is not recommended.", "danger"))
        box.pack_start(verdict, False, False, 0)
        if t.get("state") in ("running", "pending_restart"):
            box.pack_start(_label("The burn-in test that is running will be stopped.", "warn"), False, False, 0)
        self.page("Finish Setup and go live",
                  "Go Live turns on read-only mode, switches the display to Production Mode, keeps "
                  "24 hours of Performance History, and restarts. The video resumes after the restart.",
                  extra=box,
                  buttons=[("Back", self.show_current, "ghost", ""),
                           ("Go Live and restart", self.do_golive, "primary", "Waiting for the password…")])
        if self.w_ssh is not None:
            ssh_warn.set_visible(not self.w_ssh.get_active())
        self.golive_confirmed = passed

    def do_golive(self):
        if not self.golive_confirmed:
            self.golive_confirmed = True
            return self.unbusy("No passing burn-in test. Click Go Live and restart again to go live anyway.")
        if loop_state.maint_stage():
            return self.unbusy("Finish the software update first (Update Software).")
        steps = []
        if self.w_ssh is not None and self.w_ssh.get_active():
            steps.append(["ssh-off"])
        if not loop_state.ro_next():
            steps.append(["ro-on"])
        steps = steps or [["selftest"]]

        def next_step(rc=0, out=""):
            if rc:
                return self.unbusy(problem(rc, out))
            if steps:
                return run_root(steps.pop(0), next_step)
            loop_state.stop_test("Stopped at Go Live")
            loop_state.set_mode("production")
            self.restart_page("This display is going live",
                              "After the restart it runs in Production Mode with read-only protection.")
        next_step()


def open_window(parent, kind):
    if kind == "settings":
        import settings_ui
        return settings_ui.SettingsWindow(parent)
    return {"update": UpdateWindow, "setup": SetupWindow}[kind](parent)
