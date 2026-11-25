#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Help for Staff Display Tools, after the Help pages in LOTTO.

Guides are numbered Markdown files in help/ next to this script (01-getting-started.md, ...),
with screenshots in help/images. The Help window opens on an index of guide cards (title, the
guide's first paragraph as its description, and a chevron). A guide opens in the same window
with "All guides" and "Guide N of M" at the top, the article with a contents list beside it,
and Previous / Next at the bottom. Mouse-only: everything is a button, nothing needs a key.

Markdown subset: "# title", "## heading", "### heading", paragraphs, "- " bullets, "1. " steps,
"![alt](images/file.png)" (skipped if the file is missing), **bold**, `code`, and
[text](NN-guide.md) links to other guides, and {{dotted.key}} placeholders filled from the profile.
"""
import os
import re

from gi.repository import GdkPixbuf, GLib, Gtk

import loop_profile
import ui_icons
import ui_screen

HELP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "help")
IMAGE_MAX_W = 600

HELP_CSS = b"""
label.help-h1 { font-size: 24pt; color: @text@; }
label.help-lead { font-size: 12pt; color: @text_muted@; }
label.help-h2 { font-size: 16pt; color: @text@; }
label.help-h3 { font-size: 13pt; color: @text@; }
label.help-p { font-size: 12pt; color: @text_body@; }
label.help-num { font-size: 12pt; color: @link@; }
label.help-meta { font-size: 11pt; color: @text_muted@; }
label.help-toc-title { font-size: 11pt; letter-spacing: 2px; color: @text_muted@; }
label.help-caption { font-size: 11pt; color: @text_muted@; }
button.help-card {
  background-color: transparent;
  background-image: linear-gradient(to top, @card_bottom@, @surface@);
  border: 1px solid alpha(@border@, 0.85);
  border-radius: 16px;
  box-shadow: 1px 3px 10px 0 alpha(@link@, 0.20);
  padding: 14px 18px;
}
button.help-card:hover { border-color: @border_hover@; background-image: linear-gradient(to top, @card_hover_bottom@, @card_hover_top@); }
label.help-card-title { font-size: 14pt; color: @text@; }
label.help-card-desc { font-size: 11pt; color: @text_muted@; }
label.help-chevron { font-size: 16pt; color: @text_muted@; }
button.help-toc, button.help-back, button.help-link { background: none; border: none; box-shadow: none; padding: 4px 8px; }
button.help-toc label { font-size: 11pt; color: @text_muted@; }
button.help-toc:hover label, button.help-back:hover label, button.help-link:hover label { color: @link@; }
button.help-back label { font-size: 11pt; color: @text@; }
button.help-back image.lucide, button.help-nav image.lucide { color: @text_body@; }
button.help-back:hover image.lucide, button.help-nav:hover image.lucide { color: @link@; }
button.help-link label { font-size: 12pt; color: @link@; }
button.help-nav {
  background-image: linear-gradient(to top, @card_bottom@, @surface@);
  border: 1px solid alpha(@border@, 0.85);
  border-radius: 14px;
  padding: 10px 16px;
}
button.help-nav:hover { border-color: @border_hover@; }
image.help-shot { border: 1px solid alpha(@border@, 0.85); }
button.help-toc, button.help-back, button.help-link { min-height: 24px; min-width: 24px; }  /* WCAG 2.2 target size */
"""


def inline(text):
    """Markdown inline -> Pango markup: **bold**, `code`, and plain link text."""
    t = GLib.markup_escape_text(text)
    t = re.sub(r"\*\*(.+?)\*\*", r'<span weight="bold">\1</span>', t)
    t = re.sub(r"`(.+?)`", r'<span font_family="monospace">\1</span>', t)
    t = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", t)
    return t


def load_guides(folder=HELP_DIR):
    """[{slug, title, description, blocks}] in file-name order."""
    guides = []
    try:
        names = sorted(n for n in os.listdir(folder) if re.match(r"\d\d-.+\.md$", n))
    except OSError:
        return guides
    for name in names:
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            blocks = parse(loop_profile.fill(f.read()))
        title = next((b[1] for b in blocks if b[0] == "h1"), name)
        desc = next((b[1] for b in blocks if b[0] == "p"), "")
        guides.append({"slug": name, "title": title, "description": desc, "blocks": blocks})
    return guides


def parse(md):
    """Markdown -> [(kind, text, extra)]: h1/h2/h3/p/ul/ol/img."""
    blocks, para = [], []

    def flush():
        if para:
            blocks.append(("p", " ".join(para), None))
            para.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        m_img = re.match(r"!\[(.*?)\]\((.+?)\)$", line.strip())
        m_ol = re.match(r"(\d+)\.\s+(.*)", line)
        if not line.strip():
            flush()
        elif line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            blocks.append((f"h{min(level, 3)}", line.lstrip("#").strip(), None))
        elif m_img:
            flush()
            blocks.append(("img", m_img.group(1), m_img.group(2)))
        elif line.startswith("- "):
            flush()
            blocks.append(("ul", line[2:].strip(), None))
        elif m_ol:
            flush()
            blocks.append(("ol", m_ol.group(2).strip(), m_ol.group(1)))
        elif blocks and blocks[-1][0] in ("ul", "ol") and raw.startswith("  ") and not para:
            k, t, x = blocks[-1]
            blocks[-1] = (k, f"{t} {line.strip()}", x)
        else:
            para.append(line.strip())
    flush()
    return blocks


def _label(markup, cls, xalign=0.0, wrap=True, width=None):
    lb = Gtk.Label(xalign=xalign)
    lb.set_markup(markup)
    lb.get_style_context().add_class(cls)
    lb.set_line_wrap(wrap)
    if width:
        lb.set_max_width_chars(width)
    return lb


def _flat(cls, child, on_click):
    b = Gtk.Button()
    b.get_style_context().add_class(cls)
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.add(child)
    b.connect("clicked", lambda *_: on_click())
    return b


class HelpWindow(Gtk.Window):
    def __init__(self, parent, title="Help"):
        super().__init__(title=title)
        self.get_style_context().add_class("staff")
        self.set_transient_for(parent)
        ui_screen.clamp_size(self, 1180, 620)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.guides = load_guides()
        self.outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for side, px in (("top", 20), ("bottom", 20), ("start", 28), ("end", 28)):
            getattr(self.outer, f"set_margin_{side}")(px)
        self.add(self.outer)
        self.show_index()

    def _clear(self):
        for c in self.outer.get_children():
            c.destroy()

    def _top_bar(self, back_text, back_fn, meta=""):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = ui_icons.ICONS["Close"] if back_text == "Close" else ui_icons.ICONS["Back"]
        bar.pack_start(_flat("help-back", ui_icons.IconLabel(back_text, "help-p", icon=icon,
                                                              markup=f'<span weight="semibold">{back_text}</span>'),
                             back_fn), False, False, 0)
        if meta:
            bar.pack_end(_label(meta, "help-meta", xalign=1.0, wrap=False), False, False, 0)
        return bar

    # --- index of guides (LOTTO /help)
    def show_index(self):
        self._clear()
        self.outer.pack_start(self._top_bar("Close", self.destroy), False, False, 0)
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head.set_margin_top(10)
        head.pack_start(_label('<span weight="semibold">Help</span>', "help-h1"), False, False, 0)
        head.pack_start(_label("Short guides for changing the video, keeping the displays running, and "
                               "updates and setup.", "help-lead", width=90), False, False, 0)
        self.outer.pack_start(head, False, False, 0)
        if not self.guides:
            self.outer.pack_start(_label("The help guides are not installed on this display.", "help-p"),
                                  False, False, 20)
        grid = Gtk.Grid(column_spacing=16, row_spacing=16, column_homogeneous=True)
        grid.set_margin_top(20)
        for i, g in enumerate(self.guides):
            body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            text.pack_start(_label(f'<span weight="semibold">{inline(g["title"])}</span>', "help-card-title"),
                            False, False, 0)
            text.pack_start(_label(inline(g["description"]), "help-card-desc", width=40), False, False, 0)
            body.pack_start(text, True, True, 0)
            chev = _label("›", "help-chevron", wrap=False)
            chev.set_valign(Gtk.Align.START)
            body.pack_end(chev, False, False, 0)
            card = _flat("help-card", body, lambda i=i: self.show_guide(i))
            grid.attach(card, i % 2, i // 2, 1, 1)
        self.outer.pack_start(grid, False, False, 0)
        self.show_all()
        ui_screen.fit(self, body=grid)  # only the guide cards scroll; the Close link stays

    # --- one guide (LOTTO /help/[slug])
    def show_guide(self, i):
        g = self.guides[i]
        self._clear()
        self.outer.pack_start(self._top_bar("All guides", self.show_index,
                                            f"Guide {i + 1} of {len(self.guides)}"), False, False, 0)
        cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        cols.set_margin_top(8)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        article = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        article.set_margin_end(12)
        sw.add(article)
        cols.pack_start(sw, True, True, 0)
        toc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        toc.set_size_request(220, -1)
        toc.pack_start(_label('<span weight="semibold">ON THIS PAGE</span>', "help-toc-title"), False, False, 6)
        cols.pack_end(toc, False, False, 0)
        self.outer.pack_start(cols, True, True, 0)

        for kind, text, extra in g["blocks"]:
            if kind == "h1":
                article.pack_start(_label(f'<span weight="semibold">{inline(text)}</span>', "help-h1"),
                                   False, False, 0)
            elif kind in ("h2", "h3"):
                h = _label(f'<span weight="semibold">{inline(text)}</span>', f"help-{kind}")
                h.set_margin_top(14 if kind == "h2" else 8)
                article.pack_start(h, False, False, 0)
                if kind == "h2":
                    toc.pack_start(_flat("help-toc", _label(inline(text), "help-p", width=26),
                                         lambda h=h, sw=sw, a=article: self._jump(sw, a, h)), False, False, 0)
            elif kind == "p":
                article.pack_start(self._para(text, "help-lead" if article.get_children() and
                                              len(article.get_children()) == 1 else "help-p"), False, False, 0)
            elif kind in ("ul", "ol"):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.set_margin_start(6)
                mark = _label(f'<span weight="bold">{extra}.</span>' if kind == "ol" else "•", "help-num",
                              wrap=False)
                mark.set_valign(Gtk.Align.START)
                row.pack_start(mark, False, False, 0)
                row.pack_start(_label(inline(text), "help-p", width=80), True, True, 0)
                article.pack_start(row, False, False, 0)
            elif kind == "img":
                shot = self._image(extra, text)
                if shot:
                    article.pack_start(shot, False, False, 6)
        links = re.findall(r"\]\((\d\d-[^)]+\.md)\)", "".join(b[1] for b in g["blocks"]))
        for slug in dict.fromkeys(links):
            j = next((k for k, x in enumerate(self.guides) if x["slug"] == slug), None)
            if j is not None:
                article.pack_start(_flat("help-link", _label(f"See: {inline(self.guides[j]['title'])}  ›",
                                                             "help-p", wrap=False),
                                         lambda j=j: self.show_guide(j)), False, False, 0)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nav.set_margin_top(14)
        if i > 0:
            nav.pack_start(self._nav("Previous", self.guides[i - 1]["title"], lambda: self.show_guide(i - 1),
                                     0.0), False, False, 0)
        if i < len(self.guides) - 1:
            nav.pack_end(self._nav("Next", self.guides[i + 1]["title"], lambda: self.show_guide(i + 1), 1.0),
                         False, False, 0)
        self.outer.pack_start(nav, False, False, 0)
        self.show_all()
        ui_screen.fit(self)

    def _para(self, text, cls):
        return _label(inline(text), cls, width=80)

    def _nav(self, kicker, title, fn, xalign):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(_label(kicker, "help-meta", xalign=xalign, wrap=False), False, False, 0)
        row = ui_icons.IconLabel(title, "help-p", icon=ui_icons.ICONS[kicker],
                                 markup=f'<span weight="semibold">{inline(title)}</span>')
        row.set_halign(Gtk.Align.START if xalign == 0.0 else Gtk.Align.END)
        box.pack_start(row, False, False, 0)
        return _flat("help-nav", box, fn)

    def _image(self, rel, alt):
        path = os.path.join(HELP_DIR, rel)
        if not os.path.isfile(path):
            return None  # screenshot not added yet
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(path)
            max_w = ui_screen.px(IMAGE_MAX_W)  # drawn once at this screen's size, from a 2x picture: sharp
            if pb.get_width() > max_w:
                pb = pb.scale_simple(max_w, int(pb.get_height() * max_w / pb.get_width()),
                                     GdkPixbuf.InterpType.HYPER)
        except GLib.Error:
            return None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        img = Gtk.Image.new_from_pixbuf(pb)
        img._loop_scaled = True  # already sized for this screen
        img.set_halign(Gtk.Align.START)
        img.get_style_context().add_class("help-shot")
        box.pack_start(img, False, False, 0)
        box.pack_start(_label(inline(alt), "help-caption", width=80), False, False, 0)
        return box

    @staticmethod
    def _jump(sw, article, widget):
        pos = widget.translate_coordinates(article, 0, 0)
        if pos:
            sw.get_vadjustment().set_value(max(0, pos[1] - 8))


class ReleaseNotesWindow(Gtk.Window):
    """What changed in each release, newest first (help/release-notes.md), opened from the version number.
    After LOTTO's and FEED's release notes: a heading per version and one-line bullet points. The window's own
    title bar closes it."""

    def __init__(self, parent):
        super().__init__(title="Release Notes")
        self.get_style_context().add_class("staff")
        self.set_transient_for(parent)
        ui_screen.clamp_size(self, 900, 600)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.set_keep_above(True)
        try:
            with open(os.path.join(HELP_DIR, "release-notes.md"), encoding="utf-8") as f:
                blocks = parse(f.read())
        except OSError:
            blocks = [("h1", "Release Notes", None), ("p", "The release notes are not installed.", None)]
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for side, px in (("top", 20), ("bottom", 20), ("start", 28), ("end", 28)):
            getattr(outer, f"set_margin_{side}")(px)
        self.add(outer)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        body.set_margin_end(12)
        sw.add(body)
        outer.pack_start(sw, True, True, 0)
        first_p = True
        for kind, text, _extra in blocks:
            if kind == "h1":
                body.pack_start(_label(f'<span weight="semibold">{inline(text)}</span>', "help-h1"), False, False, 0)
            elif kind in ("h2", "h3"):
                h = _label(f'<span weight="semibold">{inline(text)}</span>', "help-h2")
                h.set_margin_top(14)
                body.pack_start(h, False, False, 0)
            elif kind == "p":
                body.pack_start(_label(inline(text), "help-lead" if first_p else "help-p", width=80), False, False, 0)
                first_p = False
            elif kind in ("ul", "ol"):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.set_margin_start(6)
                mark = _label("•", "help-num", wrap=False)
                mark.set_valign(Gtk.Align.START)
                row.pack_start(mark, False, False, 0)
                row.pack_start(_label(inline(text), "help-p", width=80), True, True, 0)
                body.pack_start(row, False, False, 0)
        self.show_all()
        ui_screen.scale_tree(self)
