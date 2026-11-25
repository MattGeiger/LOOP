# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""LOOP's icons: Lucide SVGs with fixed meanings (docs/DESIGN_LANGUAGE.md).

ICONS is the single table every window reads, so one action always shows the same icon. Look a control up by
its label with icon_for(); never pick an icon for one button in window code. To add one: give it a meaning in
docs/DESIGN_LANGUAGE.md, add the pinned SVG to src/icons/, then add it here.

An Icon draws its SVG in the CSS text color of where it sits (its "color" property), so it follows the label
beside it: dark on yellow buttons, light on cards, muted on inactive steps, and it changes with hover and busy
states by itself. IconLabel is the icon plus text that buttons hold; it keeps Gtk.Label's set_markup/set_text,
and set_busy() swaps the icon for a spinning loader while the button works.
"""
import html
import os
import re

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402

import ui_screen  # noqa: E402

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

# Design sizes at 1280x720 (scaled with the window): buttons, the main window's cards, step pills and tabs.
SIZES = {"button": 18, "card": 22, "pill": 14}

ICONS = {
    # Staff Display Tools
    "Setup & Burn-in": "monitor-cog",
    "Get a new video": "file-video-camera",
    "Open videos folder": "folder-open",
    "Show idle screen": "wallpaper",
    "Resume video": "monitor-play",
    "Restart video": "monitor-play",
    "Click again to restart": "monitor-play",
    "Display status": "monitor-activity",
    "Performance history": "list-clock",
    "Update Software": "refresh-cw",
    "Start fullscreen playback": "expand",
    "Help": "circle-question-mark",
    "About": "info",
    "Settings": "settings",
    "Version": "rocket",
    "Source Code on GitHub": "github",
    # Setup & Burn-in
    "Finish setup (go live)": "clapperboard",
    "Go live and restart": "clapperboard",
    "Change settings": "settings",
    "Change settings (Settings window)": "settings",
    "Start burn-in test": "flame",
    "Start another test": "flame",
    "Stop and change settings": "circle-stop",
    "Stop the burn-in test": "circle-stop",
    "Open Settings": "settings",
    # LOOP Setup steps and Settings tabs
    "Start": "circle-fading-play",
    "Organization": "user-group",
    "Video library": "file-video-camera",
    "This display": "monitor",
    "Pictures": "image-plus",
    "Colors": "palette",
    "Review": "circle-dashed-check",
    # LOOP Setup and Settings controls
    "Open LOOP Setup (step by step)": "circle-fading-play",
    "Look again": "usb",
    "Use readable": "contrast",
    "Choose a picture": "image-plus",
    "Save settings": "save",
    "Save and set up": "save",
    # Update Software steps
    "Read/write Mode": "file-cog",
    "Check for updates": "refresh-cw",
    "Set Read-only Mode": "file-lock",
    "Return to video": "monitor-play",
    # Update Software controls
    "Open Update Software": "refresh-cw",
    "Check again": "refresh-cw",
    "Skip updates & set Read-only Mode": "refresh-cw-off",
    "I understand, switch modes and restart": "file-cog",
    "Update selected": "list-checks",
    "Update all": "download",
    "Restart now": "power",
    "Repair": "wrench",
    "Repair and try again": "wrench",
    "Try again": "rotate-ccw",
    "Resume video without read-only (not recommended)": "monitor-play",
    # Everywhere
    "Close": "x",
    "Cancel": "x",
    "Cancel update": "x",
    "Done": "check",
    "Back": "arrow-left",
    "Next": "arrow-right",
    "Continue": "arrow-right",
    "Previous": "arrow-left",
}
BUSY = "loader-circle"
# Labels that carry a value after a fixed start ("Update all (12)", "Use readable #2c827f").
PREFIXES = ("Update all", "Use readable", "Choose a picture")


def icon_for(text):
    """The icon name for a control's label, or None. Markup, a trailing … and surrounding space are ignored."""
    t = re.sub(r"<[^>]+>", "", text or "").strip().rstrip("…").strip()
    t = html.unescape(t)
    if t in ICONS:
        return ICONS[t]
    return next((ICONS[p] for p in PREFIXES if t.startswith(p)), None)


_cache = {}


def _pixbuf(name, size_px, rgb):
    key = (name, size_px, rgb)
    if key not in _cache:
        with open(os.path.join(ICON_DIR, name + ".svg"), "rb") as f:
            svg = f.read().replace(b"currentColor", rgb.encode())
        loader = GdkPixbuf.PixbufLoader()
        loader.connect("size-prepared", lambda ld, _w, _h: ld.set_size(size_px, size_px))
        loader.write(svg)
        loader.close()
        _cache[key] = loader.get_pixbuf()
    return _cache[key]


class Icon(Gtk.Image):
    """One Lucide icon, drawn at a design size in the CSS color where it sits."""

    def __init__(self, name, size="button"):
        super().__init__()
        self.name = name
        self.size_px = ui_screen.px(SIZES.get(size, size) if isinstance(size, str) else size)
        self._loop_scaled = True  # drawn at screen size already; ui_screen.scale_tree leaves it alone
        self._rgb = None
        self.get_style_context().add_class("lucide")
        self.set_valign(Gtk.Align.CENTER)
        self.connect("style-updated", lambda *_: self.redraw())
        self.redraw()

    def redraw(self):
        try:
            c = self.get_style_context().get_color(self.get_state_flags())
            rgb = "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))
        except (AttributeError, TypeError, ValueError):  # no style yet (or a stand-in GTK in the tests)
            rgb = "#ffffff"
        if rgb == self._rgb:
            return
        self._rgb = rgb
        try:
            self.set_from_pixbuf(_pixbuf(self.name, self.size_px, rgb))
        except (GLib.Error, OSError):
            self.clear()


class IconLabel(Gtk.Box):
    """Icon plus text, for buttons. Behaves like the Gtk.Label it replaces (set_markup, set_text, get_text)."""

    def __init__(self, text, cls=None, icon=None, size="button", markup=None, wrap=False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8 if size != "pill" else 6)
        self.set_halign(Gtk.Align.CENTER)
        name = icon or icon_for(text)
        self.icon = Icon(name, size) if name else None
        self.spinner = Icon(BUSY, size)
        self.spinner.get_style_context().add_class("spin")
        self.spinner.set_no_show_all(True)
        self.label = Gtk.Label()
        if cls:
            self.label.get_style_context().add_class(cls)
        if wrap:
            self.label.set_line_wrap(True)
        if markup is not None:
            self.label.set_markup(markup)
        else:
            self.label.set_text(text)
        for w in (self.icon, self.spinner, self.label):
            if w is not None:
                self.pack_start(w, False, False, 0)

    def set_markup(self, markup):
        self.label.set_markup(markup)

    def set_text(self, text):
        self.label.set_text(text)

    def get_text(self):
        return self.label.get_text()

    def set_busy(self, busy):
        """Swap the icon for a spinning loader while the button works (and back)."""
        if self.icon is not None:
            self.icon.set_visible(not busy)
        self.spinner.set_visible(busy)


def set_busy(widget, busy):
    """set_busy on a button's IconLabel, if it has one."""
    child = widget.get_child() if isinstance(widget, Gtk.Bin) else widget
    if isinstance(child, IconLabel):
        child.set_busy(busy)


# Icon colors follow the text beside them; the spinner turns. Merged into each window's style sheet.
ICON_CSS = b"""
image.lucide { color: @text@; }
button.pill image.lucide { color: @on_accent@; }
button.pill.ghost image.lucide { color: @text@; }
button.card image.lucide { color: @text@; }
button.card.busy image.lucide { color: @on_accent@; }
button.card.confirm image.lucide { color: @accent@; }
button.about-link image.lucide { color: @text@; }
button.about-link:hover image.lucide { color: @link@; }
button.version-link image.lucide { color: @text_muted@; }
button.version-link:hover image.lucide { color: @link@; }
button.choose image.lucide { color: @text@; }
button.link-btn image.lucide { color: @text_muted@; }
button.link-btn.confirm image.lucide { color: @danger@; }
button.tab image.lucide { color: @text_muted@; }
button.tab.tab-active image.lucide { color: @text@; }
@keyframes loop-spin { to { -gtk-icon-transform: rotate(1turn); } }
image.lucide.spin { animation: loop-spin 1s linear infinite; }
"""
