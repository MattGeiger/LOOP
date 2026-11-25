#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""The setup wizard and the Settings window: one set of forms for LOOP's settings (loop_settings.FIELDS).

SetupWizard (the `loop-setup-wizard` command; opens by itself at the first login after LOOP is installed, until a
display is set up) walks through Start, Organization, Video library, This display, Pictures, Colors and Review,
then saves. SettingsWindow (Staff Display Tools > Settings) shows the same pages for changes after setup.

Saving writes profile.json, site.json and any new pictures to a private folder, and the privileged helper
(`loop-maintenance-root settings`, behind the administrator password) checks them and runs loop-setup. Like
software updates, settings need Read/write Mode; in Read-only Mode, Settings sends you to Update Software.
Same look and click rules as the admin windows: instant feedback, repeat clicks ignored.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_profile  # noqa: E402
import loop_settings as S  # noqa: E402
import loop_state  # noqa: E402
import staff_admin  # noqa: E402
import ui_icons  # noqa: E402
import ui_screen  # noqa: E402
from staff_admin import _bold, _label  # noqa: E402

SETTINGS_CSS = b"""
entry {
  background-color: @surface@; background-image: none; color: @text@;
  border: 1px solid alpha(@border@, 0.85); border-radius: 10px; padding: 2px 10px;
  font-size: 12pt; min-height: 24px; box-shadow: none;
}
entry:focus { border-color: @border_hover@; }
entry.bad { border-color: @danger@; }
label.field-label { font-size: 12pt; color: @text@; }
label.field-help { font-size: 11pt; color: @text_muted@; }
label.field-error { font-size: 11pt; color: @danger@; }
label.field-file { font-size: 11pt; color: @text_soft@; }
button.tab { background: none; border: none; box-shadow: none; padding: 4px 10px; border-radius: 999px; }
button.tab label { font-size: 12pt; color: @text_muted@; }
button.tab.tab-active { background-color: alpha(@accent@, 0.18); }
button.tab.tab-active label { color: @text@; }
button.tab, button.choose { min-height: 24px; min-width: 24px; }  /* WCAG 2.2 target size */
button.choose {
  background-image: linear-gradient(to top, @card_bottom@, @surface@); border: 1px solid alpha(@border@, 0.85);
  border-radius: 999px; padding: 4px 14px; box-shadow: none; text-shadow: none;
}
button.choose label { font-size: 11pt; color: @text@; }
button.color {
  background-image: linear-gradient(to top, @card_bottom@, @surface@); border: 1px solid alpha(@border@, 0.85);
  border-radius: 10px; padding: 4px 8px; box-shadow: none; min-height: 24px; min-width: 24px;
}
"""

SUMMARY_VALUE_CHARS = 56  # Review page: value column width in characters (fits the 1100 px window)
FULL_HEIGHT = 640  # design pixels (ui_screen): the tallest page fits at 720p
WIZARD_LOCK = "loop-setup-wizard.pid"  # in the runtime folder while the wizard is open (the player waits)
SETTINGS_PAGES = [("start", "Start", "Choose the look to start from. Switching replaces the organization details, "
                                     "names and colors with that profile's; Save settings applies it.")] + S.PAGES
WIZARD_STEPS = ["Start", "Organization", "Video library", "This display", "Pictures", "Colors", "Review"]
PAGE_OF_STEP = {1: "organization", 2: "library", 3: "display", 4: "pictures", 5: "colors"}
PROFILE_NOTES = {"default": "LOOP's own look (Temple Consulting). Change the pictures and colors to your own."}


def runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"


def usb_drives():
    """[(device, description)] for whole USB disks."""
    try:
        out = subprocess.run(["lsblk", "-J", "-d", "-o", "NAME,SIZE,MODEL,TRAN,TYPE,LABEL"], capture_output=True,
                             text=True, timeout=10).stdout
        disks = json.loads(out).get("blockdevices", [])
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    in_use = data_drive_disk()
    return [(f"/dev/{d['name']}", f"{(d.get('model') or 'USB drive').strip()}, {d.get('size', '?')} (/dev/{d['name']})")
            for d in disks if d.get("tran") == "usb" and d.get("type") == "disk" and d["name"] != in_use]


def data_drive_disk():
    """The disk (for example "sda") holding the data folder now, or None."""
    try:
        src = subprocess.run(["findmnt", "-n", "-o", "SOURCE", loop_profile.data_mount()], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        if not src:
            return None
        return subprocess.run(["lsblk", "-n", "-d", "-o", "PKNAME", src], capture_output=True, text=True,
                              timeout=5).stdout.strip() or os.path.basename(src)
    except (OSError, subprocess.SubprocessError):
        return None


class Form(Gtk.Box):
    """The fields of one page, with their help text and any problem shown under each."""

    def __init__(self, window, page, values, files):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window, self.page_id, self.values, self.files = window, page, values, files
        self.read_fns, self.error_labels = {}, {}
        self.color_entries, self.fix_buttons, self.suggestions = {}, {}, {}
        grid = Gtk.Grid(column_spacing=18, row_spacing=6)
        self.pack_start(grid, False, False, 0)
        row = 0
        for key, pg, kind, label, help_, _where, opt in S.FIELDS:
            if pg != page:
                continue
            name = _label(label, "field-label", wrap=False, weight="semibold", xalign=1.0)
            name.set_valign(Gtk.Align.START)
            name.set_margin_top(4)
            grid.attach(name, 0, row, 1, 1)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            col.set_hexpand(True)
            col.pack_start(self._widget(key, kind, opt), False, False, 0)
            if help_:
                h = _label(help_, "field-help")
                h.set_max_width_chars(46 if page == "colors" else 70)  # colors: beside the preview
                col.pack_start(h, False, False, 0)
            err = _label("", "field-error", weight="semibold")
            err.set_max_width_chars(46 if page == "colors" else 80)
            err.set_no_show_all(True)
            col.pack_start(err, False, False, 0)
            self.error_labels[key] = err
            grid.attach(col, 1, row, 1, 1)
            row += 1

    def _widget(self, key, kind, opt):
        val = self.values.get(key)
        if kind in ("text", "url"):
            e = Gtk.Entry()
            e.set_text("" if val is None else str(val))
            e.set_width_chars(46)
            e.set_max_length(opt.get("max", 300))
            e.connect("changed", lambda *_a, k=key: self.clear_error(k))
            self.read_fns[key] = e.get_text
            return e
        if kind == "int":
            sp = Gtk.SpinButton.new_with_range(opt.get("min", 0), opt.get("max", 100), 1)
            sp.set_value(int(val or opt.get("min", 0)))
            sp.set_halign(Gtk.Align.START)
            sp.connect("value-changed", lambda *_a, k=key: self.clear_error(k))
            self.read_fns[key] = sp.get_value_as_int
            return sp
        if kind == "rotate":
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            group, buttons = None, {}
            for deg, text in S.ROTATE_CHOICES:
                rb = Gtk.RadioButton.new_with_label_from_widget(group, f"{deg}°  {text}")
                group = group or rb
                rb.set_active(deg == val)
                rb.connect("toggled", lambda *_a, k=key: self.clear_error(k))
                buttons[deg] = rb
                box.pack_start(rb, False, False, 0)
            self.read_fns[key] = lambda: next((d for d, b in buttons.items() if b.get_active()), 0)
            return box
        if kind == "color":
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            entry = Gtk.Entry()
            entry.set_width_chars(9)
            entry.set_max_length(7)
            entry.set_text(val or "")
            swatch = Gtk.ColorButton()
            swatch.get_style_context().add_class("color")
            swatch.set_use_alpha(False)
            self._set_swatch(swatch, val)

            def from_swatch(btn):
                c = btn.get_rgba()
                entry.set_text("#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255)))

            def from_entry(e, k=key):
                self.clear_error(k)
                if S.is_color(e.get_text()):
                    self._set_swatch(swatch, e.get_text())
                    self.window.on_color_change()
            swatch.connect("color-set", from_swatch)
            entry.connect("changed", from_entry)
            box.pack_start(swatch, False, False, 0)
            box.pack_start(entry, False, False, 0)
            self.read_fns[key] = lambda: entry.get_text().strip()
            self.color_entries[key] = entry
            fix = Gtk.Button()  # one-click readable shade, shown only when the color fails
            fix.get_style_context().add_class("choose")
            fix.add(ui_icons.IconLabel("", "choose", icon=ui_icons.ICONS["Use readable"]))
            fix.set_no_show_all(True)
            fix.connect("clicked", lambda *_a, k=key: self.apply_suggestion(k))
            self.fix_buttons[key] = fix
            box.pack_start(fix, False, False, 0)
            return box
        if kind == "image":
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            btn = Gtk.Button()
            btn.get_style_context().add_class("choose")
            btn.add(ui_icons.IconLabel("Choose a picture…", "choose", markup=_bold("Choose a picture…", "semibold")))
            shown = _label(self._file_text(key, opt), "field-file", wrap=False)
            shown.set_ellipsize(Pango.EllipsizeMode.MIDDLE)  # a long file name never widens the window
            shown.set_max_width_chars(48)
            btn.connect("clicked", lambda *_: self._choose(key, opt, shown))
            box.pack_start(btn, False, False, 0)
            box.pack_start(shown, False, False, 0)
            return box
        raise ValueError(kind)

    @staticmethod
    def _set_swatch(swatch, val):
        rgba = Gdk.RGBA()
        if S.is_color(val) and rgba.parse(val):
            swatch.set_rgba(rgba)

    def _file_text(self, key, opt):
        if self.files.get(key):
            return "New: " + os.path.basename(self.files[key])
        current = None
        for ext in opt["types"]:
            current = current or loop_profile.asset(f"{opt['name']}.{ext}")
        return "Current picture kept" if current else "None yet (LOOP's own is used)"

    def _choose(self, key, opt, shown):
        dlg = Gtk.FileChooserDialog(title="Choose a picture", transient_for=self.window,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Use this picture", Gtk.ResponseType.OK)
        dlg.set_keep_above(True)
        flt = Gtk.FileFilter()
        flt.set_name(" or ".join(t.upper() for t in opt["types"]))
        for t in opt["types"]:
            flt.add_pattern(f"*.{t}")
            flt.add_pattern(f"*.{t.upper()}")
            if t == "jpg":
                flt.add_pattern("*.jpeg")
        dlg.add_filter(flt)
        if os.path.isdir(os.path.expanduser("~/Downloads")):
            dlg.set_current_folder(os.path.expanduser("~/Downloads"))
        if dlg.run() == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            problem = S.picture_problem(path, opt["types"])
            if problem:
                self.show_errors({key: problem})
            else:
                self.files[key] = path
                shown.set_text(self._file_text(key, opt))
                self.show_errors({})
        dlg.destroy()

    def read(self):
        for key, fn in self.read_fns.items():
            self.values[key] = fn()
        self.values.update({k: v for k, v in self.files.items() if v})
        return self.values

    def update_suggestions(self, base, values=None):
        """Offer the nearest readable shade next to any color that fails its contrast check."""
        for key, entry in self.color_entries.items():
            fix = S.readable_suggestion(key, entry.get_text().strip(), base, values)
            self.suggestions[key] = fix
            btn = self.fix_buttons[key]
            if fix:
                btn.get_child().set_markup(f'<span weight="semibold">Use readable {fix}</span>')
                btn.get_child().show_all()
                btn.show()  # (show_all is ignored on a no-show-all widget)
            else:
                btn.hide()

    def apply_suggestion(self, key):
        if self.suggestions.get(key):
            self.color_entries[key].set_text(self.suggestions[key])

    def clear_error(self, key):
        lb = self.error_labels.get(key)
        if lb is not None and lb.get_visible():
            lb.set_visible(False)
            self.window.say("")

    def show_errors(self, errors):
        for key, lb in self.error_labels.items():
            text = errors.get(key, "")
            lb.set_markup(_bold(text, "semibold") if text else "")
            lb.set_visible(bool(text))


class Preview(Gtk.Box):
    """A small sample of Staff Display Tools in the chosen colors: heading, text, a card and the main button."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.provider = Gtk.CssProvider()
        self.get_style_context().add_class("loop-preview")
        self.set_valign(Gtk.Align.START)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.connect("destroy", lambda *_: Gtk.StyleContext.remove_provider_for_screen(
            Gdk.Screen.get_default(), self.provider))
        self.pack_start(_label("PREVIEW", "pv-eyebrow", wrap=False, weight="semibold"), False, False, 0)
        self.pack_start(_label("Now showing", "pv-text", wrap=False, weight="semibold"), False, False, 0)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("pv-card")
        head = ui_icons.IconLabel("Restart video", "pv-text", markup=_bold("Restart video"))
        head.set_halign(Gtk.Align.START)
        card.pack_start(head, False, False, 0)
        card.pack_start(_label("Use if the screen looks stuck.", "pv-muted", wrap=False), False, False, 0)
        self.pack_start(card, False, False, 0)
        self.pack_start(_label("Message text in the button color", "pv-msg", wrap=False, weight="bold"),
                        False, False, 0)
        pill = Gtk.Box()
        pill.get_style_context().add_class("pv-pill")
        pill.set_halign(Gtk.Align.START)
        pill.add(ui_icons.IconLabel("Start fullscreen playback", "pv-pill-text",
                                    markup=_bold("Start fullscreen playback")))
        self.pack_start(pill, False, False, 0)
        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chips.pack_start(_label("  Menu highlight  ", "pv-hl", wrap=False, weight="semibold"), False, False, 0)
        chips.pack_start(_label("  Desktop  ", "pv-desk", wrap=False, weight="semibold"), False, False, 0)
        self.pack_start(chips, False, False, 0)

    def update(self, theme, desktop, highlight):
        css = f"""
        box.loop-preview {{ background-color: {theme['bg_start']}; border-radius: 16px; padding: 14px 18px;
                           border: 1px solid {theme['border']};
                           background-image: linear-gradient(170deg, {theme['bg_start']}, {theme['bg_mid']},
                                                             {theme['bg_end']}); }}
        label.pv-eyebrow {{ color: {theme['text_muted']}; font-size: 11pt; letter-spacing: 3px; }}
        label.pv-text {{ color: {theme['text']}; font-size: 13pt; }}
        label.pv-muted {{ color: {theme['text_muted']}; font-size: 11pt; }}
        box.pv-card {{ background-image: linear-gradient(to top, {theme['card_bottom']}, {theme['surface']});
                      border: 1px solid {theme['border']}; border-radius: 14px; padding: 10px 14px; }}
        box.pv-pill {{ background-image: linear-gradient(to top, {theme['accent_deep']}, {theme['accent']});
                      border-radius: 999px; padding: 8px 20px; }}
        label.pv-pill-text {{ color: {theme['on_accent']}; font-size: 12pt; }}
        box.pv-pill image.lucide {{ color: {theme['on_accent']}; }}
        box.pv-card image.lucide {{ color: {theme['text']}; }}
        label.pv-msg {{ color: {theme['accent']}; font-size: 12pt; }}
        label.pv-desk {{ background-color: {desktop}; color: #ffffff; font-size: 11pt; padding: 4px 8px;
                        border-radius: 6px; border: 1px solid alpha(#ffffff, 0.25); }}
        label.pv-hl {{ background-color: {highlight}; color: #ffffff; font-size: 11pt; padding: 4px 8px;
                      border-radius: 6px; }}
        """
        self.provider.load_from_data(ui_screen.scale_css(css))


class SettingsBase(staff_admin.AdminWindow):
    """Shared by the wizard and Settings: the values being edited, the forms, checking and saving."""

    def __init__(self, parent, title, eyebrow):
        super().__init__(parent, title, eyebrow)
        # Open at full size: under Wayland a window can't move itself, so one that grows after it is placed can
        # run off the bottom of the screen. The middle part fills the space and the buttons stay at the bottom.
        _w, h = ui_screen.workarea()
        self.fit_max = min(ui_screen.px(FULL_HEIGHT), h - ui_screen.TITLE_AND_MARGIN)  # all the screen allows
        self.set_size_request(ui_screen.px(1100), self.fit_max)
        outer = self.fit_body.get_parent()
        outer.set_child_packing(self.fit_body, True, True, 0, Gtk.PackType.START)
        self.values = S.current()
        self.files = {}  # field key -> chosen picture
        self.drive = None
        self.form = None
        self.preview = None
        self.original_base = self.values.get("base") or "default"
        self.reset_pictures = False

    def form_for(self, page):
        if self.form is not None:
            self.form.read()
        self.form = Form(self, page, self.values, self.files)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.preview = None
        if page == "colors":  # the preview sits beside the fields, so the page fits a 720p screen
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
            row.pack_start(self.form, True, True, 0)
            self.preview = Preview()
            self.preview.set_size_request(330, -1)
            row.pack_end(self.preview, False, False, 0)
            box.pack_start(row, False, False, 0)
            GLib.idle_add(lambda: (self.on_color_change(), False)[1])
        else:
            box.pack_start(self.form, False, False, 0)
        return box

    def on_color_change(self):
        if self.preview is None or self.form is None:
            return
        vals = dict(self.values)
        for key, fn in self.form.read_fns.items():
            vals[key] = fn()
        base = S.base_config(vals.get("base") or S.base_name())
        theme = S.full_theme(vals)
        desktop = vals.get("colors.desktop") if S.is_color(vals.get("colors.desktop")) else base["colors"]["desktop"]
        highlight = vals.get("colors.accent") if S.is_color(vals.get("colors.accent")) else base["colors"]["accent"]
        self.preview.update(theme, desktop, highlight)
        self.form.update_suggestions(vals.get("base") or S.base_name(), vals)

    def page_errors(self, page):
        if self.form is not None:
            self.form.read()
        errors = S.validate(self.values)
        mine = {k: v for k, v in errors.items() if S.FIELD.get(k, (None, None))[1] == page}
        if self.form is not None:
            self.form.show_errors(mine)
        return mine, errors

    def save(self, on_saved):
        if self.form is not None:
            self.form.read()
        if hasattr(self, "drive_buttons") and self.drive_buttons is not None and getattr(self, "drive_options", None) \
                is not None and self.drive_problem():
            self.unbusy(self.drive_problem())
            return
        errors = S.validate(self.values)
        if errors:
            first = next(iter(errors))
            self.unbusy("Some settings need attention: " + errors[first])
            self.goto_field(first, errors)
            return
        try:
            folder = tempfile.mkdtemp(prefix="loop-settings-", dir=runtime_dir())
            profile, site = S.build(self.values, S.existing_site())
            json.dump(profile, open(os.path.join(folder, "profile.json"), "w"), indent=2)
            json.dump(site, open(os.path.join(folder, "site.json"), "w"), indent=2)
            if self.reset_pictures:
                open(os.path.join(folder, S.RESET_MARK), "w").close()
            for key, path in self.files.items():
                if path:
                    ext = os.path.splitext(path)[1].lower().replace(".jpeg", ".jpg")
                    shutil.copyfile(path, os.path.join(folder, S.FIELD[key][6]["name"] + ext))
        except OSError as e:
            self.unbusy(f"Could not prepare the settings: {e}")
            return
        self.say("Saving. Type the administrator password when asked…")
        args = ["settings", folder] + ([self.drive] if self.drive else [])

        def done(rc, out):
            shutil.rmtree(folder, ignore_errors=True)
            if rc == 0:
                loop_profile.load(refresh=True)
                on_saved(out)
            else:
                self.unbusy(staff_admin.problem(rc, out))
        staff_admin.run_root(args, done)

    def goto_field(self, key, errors):
        raise NotImplementedError

    def drive_picker(self):
        """The USB data drive: videos, the display's state and Performance history live on it, so they survive
        Read-only Mode and restarts. Required: setup can't finish without one."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.pack_start(_label("USB data drive (videos, the display's state and Performance history)", "field-label",
                              weight="semibold"), False, False, 0)
        mount = loop_profile.data_mount()
        group, self.drive_buttons = None, {}
        options = []
        if os.path.ismount(mount):
            options.append((None, f"Keep the data drive already set up ({mount})"))
        options += [(dev, f"ERASE and use: {desc}") for dev, desc in usb_drives()]
        self.drive_options = options
        if not options:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.pack_start(_label("No USB drive found. Plug one in (it will be erased), then click Look again. "
                                  "Read-only Mode keeps the SD card safe, so the videos and history need it.",
                                  "warn"), True, True, 0)
            again = Gtk.Button()
            again.get_style_context().add_class("choose")
            again.set_valign(Gtk.Align.CENTER)
            again.add(ui_icons.IconLabel("Look again", "choose", markup=_bold("Look again", "semibold")))
            again.connect("clicked", lambda *_: self.refresh_drives())
            row.pack_start(again, False, False, 0)
            box.pack_start(row, False, False, 0)
        for dev, text in options:
            rb = Gtk.RadioButton.new_with_label_from_widget(group, text)
            group = group or rb
            rb.set_active(dev == self.drive)
            self.drive_buttons[dev] = rb
            box.pack_start(rb, False, False, 0)
        self.erase_ok = Gtk.CheckButton.new_with_label("I understand everything on the chosen drive will be erased")
        self.erase_ok.set_active(bool(self.drive))
        if any(dev for dev, _t in options):  # only when a drive could be erased
            box.pack_start(self.erase_ok, False, False, 0)
        return box

    def refresh_drives(self):
        raise NotImplementedError

    def drive_problem(self):
        if not getattr(self, "drive_options", None):
            return "Plug in a USB drive for the videos, then click Look again."
        self.drive = next((d for d, b in getattr(self, "drive_buttons", {}).items() if b.get_active()), None)
        if self.drive and not self.erase_ok.get_active():
            return "Tick the box to confirm the drive may be erased, or choose to keep the current drive."
        return None

    def start_box(self, live=False):
        """Where to start from: a packaged profile (LOOP's default look or an organization's). Choosing a different
        one replaces the organization details, names and colors with that profile's; pictures added earlier can be
        removed so the profile's own are used. live: apply as soon as a choice is clicked (Settings)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(_label("Start from", "field-label", weight="semibold"), False, False, 0)
        group, self.base_buttons = None, {}
        current = self.values.get("base") or "default"
        for name in S.packaged_profiles():
            cfg = S.base_config(name)
            org = cfg["identity"].get("organization") or "LOOP default"
            rb = Gtk.RadioButton.new_with_label_from_widget(group, f"{org}  ({name})")
            rb.get_child().set_line_wrap(True)
            rb.get_child().set_max_width_chars(70)
            group = group or rb
            rb.set_active(name == current)
            self.base_buttons[name] = rb
            box.pack_start(rb, False, False, 0)
            if PROFILE_NOTES.get(name):
                note = _label(PROFILE_NOTES[name], "field-help")
                note.set_margin_start(28)
                box.pack_start(note, False, False, 0)
        self.reset_check = Gtk.CheckButton.new_with_label(
            "Also use this profile's pictures (removes the logo, icon and idle pictures added earlier)")
        self.reset_check.set_margin_top(8)
        self.reset_check.set_no_show_all(True)
        box.pack_start(self.reset_check, False, False, 0)

        def toggled(_rb):
            chosen = next((n for n, b in self.base_buttons.items() if b.get_active()), "default")
            show = bool(S.own_pictures()) and chosen != self.original_base
            self.reset_check.set_visible(show)
            self.reset_check.set_active(show)
            if live:
                self.apply_base(chosen)
        for rb in self.base_buttons.values():
            rb.connect("toggled", toggled)
        return box

    def apply_base(self, chosen):
        if chosen != self.values.get("base"):
            ref = S.base_config(chosen)  # the new starting point's identity, names and colors
            for key, _pg, kind, _l, _h, where, _o in S.FIELDS:
                if where == "profile":
                    self.values[key] = S._get(ref, key)
            self.values["base"] = chosen
        self.reset_pictures = bool(self.reset_check.get_visible() and self.reset_check.get_active())

    def summary(self):
        """The settings as text for the Review page."""
        rows = [("Starting point", f"{self.values.get('base') or 'default'} profile")]
        for key, _pg, kind, label, _h, _w, _o in S.FIELDS:
            if kind == "image":
                val = os.path.basename(self.files[key]) if self.files.get(key) else "(unchanged)"
            elif kind == "rotate":
                val = dict(S.ROTATE_CHOICES).get(self.values.get(key), "?")
            else:
                val = self.values.get(key)
                val = "(none)" if val in (None, "") else str(val)
            rows.append((label, val))
        if self.drive:
            rows.append(("Data drive", f"ERASE {self.drive} and use it for videos and history"))
        width = max(len(k) for k, _v in rows) + 3
        lines = []
        for k, v in rows:  # long values (a library link) wrap under their column, never widening the window
            parts = textwrap.wrap(v, SUMMARY_VALUE_CHARS, break_long_words=True, break_on_hyphens=False) or [""]
            lines.append(f"{k + ':':<{width}}{parts[0]}")
            lines += [" " * width + part for part in parts[1:]]
        return "\n".join(lines)

    def warnings(self):
        rot = self.values.get("display.rotate")
        src = loop_profile.idle_source(rot) or ""
        if rot in (90, 270) and not self.files.get("file.idle_portrait") and \
                not src.endswith(("-portrait.png", "-portrait.jpg")):
            return ("This TV is on its side but there is no idle picture made for it, so the landscape picture "
                    "is shown turned, with bars. Add a 1080 x 1920 picture on the Pictures page.")
        return None


# ================================================================ setup wizard
class SetupWizard(SettingsBase):
    def __init__(self):
        super().__init__(None, "LOOP Setup", "SETUP WIZARD")
        self.connect("destroy", Gtk.main_quit)  # stays above the video, like Staff Display Tools
        import staff_tools
        self.title_box.pack_start(staff_tools.version_link(self, self.open_release_notes), False, False, 0)
        self.notes_win = None
        self.about_win = self.help_win = None
        self.step = 0
        self.reached = 0  # the furthest step reached through Next: every step up to it is complete
        self.show_step()

    def show_current(self):
        self.show_step()

    def step_pill(self, i, name, active):
        """A clickable step. Steps up to the furthest one reached can be opened; later ones are muted and
        ignore clicks, so a step opens only once the one before it is complete."""
        pill = Gtk.Button()
        pill.set_relief(Gtk.ReliefStyle.NONE)
        ctx = pill.get_style_context()
        ctx.add_class("step")
        done = active is not None and active >= len(WIZARD_STEPS)  # set up: nothing left to go back to
        open_ = not done and i <= self.reached and i != active
        if active is not None and i < active:
            ctx.add_class("step-done")
        elif i == active:
            ctx.add_class("step-active")
        if not open_ and i != active:
            ctx.add_class("step-muted")
            pill.set_tooltip_text("Complete the steps before this one first.")
        pill.add(ui_icons.IconLabel(name, size="pill"))
        pill.connect("clicked", lambda *_a: self.goto_step(i) if open_ else None)
        return pill

    def goto_step(self, i):
        if self.busy or i == self.step or i > self.reached:
            return
        if self.step in PAGE_OF_STEP and i > self.step:  # going forward: this page must be complete first
            page = PAGE_OF_STEP[self.step]
            mine, _all = self.page_errors(page)
            if page == "display" and self.drive_problem():
                mine["drive"] = self.drive_problem()
            if mine:
                return self.unbusy(next(iter(mine.values())))
        elif self.form is not None:
            self.form.read()
        self.step = i
        self.show_step()

    def page(self, *args, **kwargs):
        """Every page: Help and About at the bottom left, as in Staff Display Tools, so people can read about
        LOOP before setting it up."""
        super().page(*args, **kwargs)
        links = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        links.set_valign(Gtk.Align.CENTER)
        for text, fn in (("Help", self.open_help), ("About", self.open_about)):
            b = Gtk.Button()
            b.get_style_context().add_class("about-link")
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.add(ui_icons.IconLabel(text, "about-link", markup=_bold(text, "semibold")))
            b.connect("clicked", lambda *_a, fn=fn: fn())
            links.pack_start(b, False, False, 0)
        self.foot.pack_start(links, False, False, 0)
        self.foot.reorder_child(links, 0)
        links.show_all()

    def open_help(self):
        if self.help_win is not None:
            return self.help_win.present()
        import staff_help
        self.help_win = staff_help.HelpWindow(self)
        self.help_win.connect("destroy", lambda *_: setattr(self, "help_win", None))

    def open_release_notes(self):
        if self.notes_win is not None:
            return self.notes_win.present()
        import staff_help
        self.notes_win = staff_help.ReleaseNotesWindow(self)
        self.notes_win.connect("destroy", lambda *_: setattr(self, "notes_win", None))

    def open_about(self):
        if self.about_win is not None:
            return self.about_win.present()
        import staff_tools
        self.about_win = staff_tools.AboutWindow(self)
        self.about_win.connect("destroy", lambda *_: setattr(self, "about_win", None))

    def show_step(self):
        self.reached = max(self.reached, self.step)
        self.form = None if self.step in (0, 6) else self.form
        if self.step == 0:
            return self.p_start()
        if self.step == 6:
            return self.p_review()
        page = PAGE_OF_STEP[self.step]
        title, intro = next((t, i) for p, t, i in S.PAGES if p == page)
        self.form = None
        extra = self.form_for(page)
        if page == "display":
            extra.pack_start(self.drive_picker(), False, False, 0)
        self.page(title, intro, WIZARD_STEPS, self.step, extra=extra,
                  buttons=[("Back", self.back, "ghost", ""), ("Next", self.next, "primary", "")])

    def p_start(self):
        box = self.start_box()
        self.page("Set up this display",
                  "LOOP plays your videos on a loop, by themselves, and gives staff simple controls. These steps "
                  "collect your organization's details, the link to your video library, how this TV is mounted, "
                  "and your logos and colors. You can change any of them later in Staff Display Tools > Settings.",
                  WIZARD_STEPS, 0, extra=box, buttons=[("Start", self.start, "primary", "")])

    def start(self):
        self.apply_base(next((n for n, b in self.base_buttons.items() if b.get_active()), "default"))
        self.step = 1
        self.show_step()

    def next(self):
        page = PAGE_OF_STEP[self.step]
        mine, _all = self.page_errors(page)
        if page == "display" and self.drive_problem():
            mine["drive"] = self.drive_problem()
        if mine:
            self.unbusy(next(iter(mine.values())))
            return
        self.step += 1
        self.show_step()

    def back(self):
        if self.form is not None:
            self.form.read()
        self.step -= 1
        self.show_step()

    def refresh_drives(self):
        if self.form is not None:
            self.form.read()
        self.show_step()

    def goto_field(self, key, errors):
        page = S.FIELD[key][1]
        self.step = next(s for s, p in PAGE_OF_STEP.items() if p == page)
        self.show_step()
        self.form.show_errors({k: v for k, v in errors.items() if S.FIELD[k][1] == page})
        self.say("Please fix the highlighted setting.")

    def p_review(self):
        panel = Gtk.ScrolledWindow()  # the button row must stay in view at 720p
        panel.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)  # never wider than the window
        panel.get_style_context().add_class("report-scroll")
        panel.set_size_request(-1, 290)
        panel.add(_label(self.summary(), "panel-text", wrap=False))
        rw = loop_state.ro_now()
        self.page("Review and save", "Check your settings, then save. Saving asks for the administrator password, "
                  "then sets up the display (about a minute; making the idle video takes the longest).",
                  WIZARD_STEPS, 6, extra=panel, warn=self.warnings(),
                  danger=("Read-only Mode is on, so settings can't be saved. Turn it off first (Staff Display "
                          "Tools > Update Software)." if rw else None),
                  buttons=[("Back", self.back, "ghost", ""),
                           ("Save and set up", lambda: self.save(self.p_done), "primary", "Setting up…")])

    def p_done(self, out):
        self.page("This display is set up",
                  "Videos, downloads, the display's state and Performance history are kept on the USB data drive. "
                  "Use Get a new video in Staff Display Tools to add the first video from your library. "
                  "Next, open Setup & Burn-in and start the burn-in test: it switches the display to Read-only "
                  "Mode, which protects the SD card, and going live keeps it there.",
                  WIZARD_STEPS, 7, buttons=[("Close", self.destroy, "primary", "")])


# ================================================================ Settings (in Staff Display Tools)
class SettingsWindow(SettingsBase):
    def __init__(self, parent):
        super().__init__(parent, "Settings", "SETTINGS")
        self.page_id = "start"
        self.show_current()

    def show_current(self):
        if loop_state.ro_now():
            return self.p_readonly()
        self.show_page(self.page_id)

    def tabs(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for pid, title, _intro in SETTINGS_PAGES:
            b = Gtk.Button()
            b.get_style_context().add_class("tab")
            if pid == self.page_id:
                b.get_style_context().add_class("tab-active")
            b.add(ui_icons.IconLabel(title, "tab", size="pill", markup=_bold(title, "semibold")))
            b.connect("clicked", lambda _b, pid=pid: self.switch(pid))
            row.pack_start(b, False, False, 0)
        return row

    def switch(self, pid):
        if self.busy:
            return
        if self.form is not None:
            self.form.read()
        self.page_id = pid
        self.show_page(pid)

    def show_page(self, pid, msg=""):
        title, intro = next((t, i) for p, t, i in SETTINGS_PAGES if p == pid)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        if self.form is not None:
            self.form.read()
            self.form = None
        if pid == "start":
            box.pack_start(_label(intro, "step-body"), False, False, 0)
            box.pack_start(self.start_box(live=True), False, False, 0)
            wiz = Gtk.Button()
            wiz.get_style_context().add_class("choose")
            wiz.set_halign(Gtk.Align.START)
            wiz.set_margin_top(10)
            wiz.add(ui_icons.IconLabel("Open LOOP Setup (step by step)", "choose",
                                       markup=_bold("Open LOOP Setup (step by step)", "semibold")))
            wiz.connect("clicked", lambda *_: self.open_wizard())
            box.pack_start(wiz, False, False, 0)
        else:
            box.pack_start(self.form_for(pid), False, False, 0)
            if pid == "display":
                box.pack_start(self.drive_picker(), False, False, 0)
        self.page(title, "", extra=box, warn=self.warnings() if pid in ("display", "pictures") else None,
                  buttons=[("Close", self.destroy, "ghost", ""),
                           ("Save settings", lambda: self.save(self.saved), "primary", "Saving…")], msg=msg)
        self.steps.pack_start(self.tabs(), False, False, 0)  # the page tabs stay in view, like the wizard's steps
        self.steps.show_all()

    def refresh_drives(self):
        self.show_page("display")

    def open_wizard(self):
        """The whole setup, step by step, from the Start step (its Save replaces these settings)."""
        subprocess.Popen(["loop-setup-wizard"], start_new_session=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        self.destroy()

    def goto_field(self, key, errors):
        self.page_id = S.FIELD[key][1]
        self.show_page(self.page_id, "Please fix the highlighted setting.")
        self.form.show_errors({k: v for k, v in errors.items() if S.FIELD[k][1] == self.page_id})

    def saved(self, out):
        self.files = {}
        self.show_page(self.page_id, "Settings saved. Staff Display Tools shows them the next time it opens.")

    def p_readonly(self):
        self.page("Settings need Read/write Mode",
                  "Like software updates, settings can only be saved while Read-only Mode is off; otherwise they "
                  "would be lost at the next restart. Update Software turns it off (one restart), lets you change "
                  "settings, and turns it back on.",
                  buttons=[("Close", self.destroy, "ghost", ""),
                           ("Open Update Software", self.to_update, "primary", "Opening…")])

    def to_update(self):
        parent = self.get_transient_for()
        self.destroy()
        if parent is not None and hasattr(parent, "open_admin"):
            parent.open_admin("update")


def load_css():
    import staff_help
    import staff_tools
    css = staff_tools.CSS + staff_admin.ADMIN_CSS + staff_help.HELP_CSS + SETTINGS_CSS
    provider = Gtk.CssProvider()
    provider.load_from_data(ui_screen.scale_css(loop_profile.themed_css(css)))
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)


def wizard_main():
    """loop-setup-wizard [--if-needed]: --if-needed (the login autostart) does nothing once a display is set up."""
    if "--if-needed" in sys.argv and os.path.isfile("/etc/loop/site.json"):
        return 0
    if "--if-needed" in sys.argv and (os.environ.get("USER") == "rpi-first-boot-wizard" or
                                      subprocess.run(["pgrep", "-x", "piwiz"], capture_output=True).returncode == 0):
        return 0  # Raspberry Pi OS's own first-boot setup is running; LOOP Setup waits for the real user's login
    # While the wizard is open the player waits (display_player.py), so saving, which restarts the player,
    # never puts the fullscreen video over the wizard. Only one wizard at a time.
    lock = os.path.join(runtime_dir(), WIZARD_LOCK)
    try:
        os.kill(int(open(lock).read().strip()), 0)
        return 0  # already open
    except (OSError, ValueError):
        pass
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    try:
        import staff_tools
        staff_tools.set_app_identity("loop-setup-wizard")
        load_css()
        SetupWizard()
        Gtk.main()
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(wizard_main())
