# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""One 16:9 layout for every screen size.

Every Staff Display Tools window is designed for a 1280 x 720 screen: with the taskbar and title bar, its
content fits in about 1216 x 620 pixels. Every HD, Full HD, 4K and 8K television has the same 16:9 shape, so
on a larger screen everything is multiplied by the same factor (1.5 at 1080p, 3 at 4K) and the window looks
the same, filling the same share of the screen.

  scale()         the factor for this screen (never below 1, so text never shrinks below its design size)
  px(n)           a design size in pixels, scaled
  scale_css(css)  multiply every pt and px size in a style sheet
  fit(window)     after a window is shown: scale its margins, spacing and images, and if it is still taller
                  than the screen (a screen smaller than 720p, or very long content), let only its middle
                  part scroll. The button row stays in view.
  clamp_size()    set_default_size in design pixels, never larger than the usable screen area
"""
import os
import re

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

DESIGN_W, DESIGN_H = 1280, 720
TITLE_AND_MARGIN = 96  # window title bar, taskbar and a little breathing room, in screen pixels
_scale = None


def _monitor():
    display = Gdk.Display.get_default()
    return display.get_primary_monitor() or (display.get_monitor(0) if display.get_n_monitors() else None)


def workarea():
    """(width, height) of the usable screen area, or a 1080p guess if it can't be read."""
    try:
        area = _monitor().get_workarea()
        return int(area.width), int(area.height)
    except (AttributeError, TypeError, ValueError):
        return 1920, 1080


def scale():
    """Screen size / 1280 x 720 (the smaller of width and height), at least 1. LOOP_UI_SCALE overrides."""
    global _scale
    if _scale is None:
        try:
            _scale = float(os.environ["LOOP_UI_SCALE"])
        except (KeyError, ValueError):
            try:
                g = _monitor().get_geometry()
                _scale = min(g.width / DESIGN_W, g.height / DESIGN_H)
            except (AttributeError, TypeError, ValueError, ZeroDivisionError):
                _scale = 1.5
        _scale = max(1.0, _scale)
    return _scale


def px(n):
    return int(round(n * scale()))


def scale_css(css):
    """Multiply every pt and px size in a style sheet (bytes or str in, bytes out). 999px pill radii stay."""
    s = scale()
    text = css.decode() if isinstance(css, bytes) else css

    def mul(m):
        v = float(m.group(1))
        if v >= 999:
            return m.group(0)
        out = v * s
        out = max(1, round(out)) if m.group(2) == "px" and v >= 1 else round(out, 1)
        return f"{out:g}{m.group(2)}"
    return re.sub(r"(?<![\w.#-])(\d+(?:\.\d+)?)(pt|px)\b", mul, text).encode()


def scale_tree(widget):
    """Scale the design-pixel margins, spacing, size requests and images of a widget tree, once each."""
    s = scale()
    if s == 1.0:
        return
    stack = [widget]
    while stack:
        w = stack.pop()
        if isinstance(w, Gtk.Container):
            stack.extend(w.get_children())
        if getattr(w, "_loop_scaled", False) or isinstance(w, Gtk.Window):
            continue
        w._loop_scaled = True
        for side in ("top", "bottom", "start", "end"):
            v = getattr(w, f"get_margin_{side}")()
            if v:
                getattr(w, f"set_margin_{side}")(int(round(v * s)))
        if isinstance(w, Gtk.Box) and w.get_spacing():
            w.set_spacing(int(round(w.get_spacing() * s)))
        if isinstance(w, Gtk.Grid):
            w.set_row_spacing(int(round(w.get_row_spacing() * s)))
            w.set_column_spacing(int(round(w.get_column_spacing() * s)))
        rw, rh = w.get_size_request()
        if (rw > 0 or rh > 0) and not isinstance(w, Gtk.ScrolledWindow):
            w.set_size_request(int(round(rw * s)) if rw > 0 else rw, int(round(rh * s)) if rh > 0 else rh)
        if isinstance(w, Gtk.Image) and w.get_storage_type() == Gtk.ImageType.PIXBUF:
            pb = w.get_pixbuf()
            if pb is not None:
                w.set_from_pixbuf(pb.scale_simple(int(round(pb.get_width() * s)), int(round(pb.get_height() * s)),
                                                  GdkPixbuf.InterpType.BILINEAR))


def image(path, height):
    """A Gtk.Image of a picture file, drawn at a design height (scaled for this screen, sharp at any size)."""
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, -1, px(height), True)
    except GLib.Error:
        return Gtk.Image()
    img = Gtk.Image.new_from_pixbuf(pb)
    img._loop_scaled = True
    return img


def _natural_height(widget, width):
    _m, nat = widget.get_preferred_height_for_width(width)
    return max(widget.get_allocated_height(), nat)


def _scroll_in_place(window, body, height):
    """Put body in a vertical scroll area of the given height, in the same place in its parent."""
    parent = body.get_parent()
    width = body.get_allocated_width()
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_size_request(width, height)  # min-content-width is ignored without horizontal scrolling
    if isinstance(parent, Gtk.Box):
        expand, fill, padding, pack_type = parent.query_child_packing(body)
        pos = parent.child_get_property(body, "position")
        parent.remove(body)
        sw.add(body)
        (parent.pack_end if pack_type == Gtk.PackType.END else parent.pack_start)(sw, True, True, padding)
        parent.reorder_child(sw, pos)
    else:
        parent.remove(body)
        sw.add(body)
        parent.add(sw)
    sw.show_all()
    return sw


def fit(window, body=None):
    """Scale a shown window's layout for this screen, and if it is still taller than the screen, let `body`
    (its middle part; default: everything) scroll. Safe to call again whenever the content changes, for
    example a new page in an admin window."""
    body = body or getattr(window, "fit_body", None) or window.get_child()
    scale_tree(window)

    def check():
        try:
            _w, h = workarea()
            room = max(320, h - TITLE_AND_MARGIN)
            room = min(room, getattr(window, "fit_max", room))  # a window that must never grow past its size
            if body.get_parent() is None:
                return False  # page replaced meanwhile
            wrapper = body.get_parent()
            wrapper = wrapper.get_parent() if isinstance(wrapper, Gtk.Viewport) else wrapper
            wrapped = isinstance(wrapper, Gtk.ScrolledWindow) and getattr(wrapper, "_loop_fit", False)
            width = body.get_allocated_width()
            body_h = _natural_height(body, width)
            if wrapped:
                others = _natural_height(window, window.get_allocated_width()) - wrapper.get_size_request()[1]
                wrapper.set_size_request(width, max(160, min(body_h, room - others)))
                return False
            win_h = _natural_height(window, window.get_allocated_width())
            if win_h <= room:
                return False
            sw = _scroll_in_place(window, body, max(160, body_h - (win_h - room)))
            sw._loop_fit = True
            window.resize(window.get_allocated_width(), room)
        except (AttributeError, TypeError, ValueError):
            pass
        return False
    GLib.timeout_add(200, check)  # after GTK has laid the window out


def clamp_size(window, width, height):
    """set_default_size in design pixels (scaled), never larger than the usable screen area."""
    w, h = workarea()
    window.set_default_size(min(px(width), w - 32), min(px(height), h - TITLE_AND_MARGIN))
