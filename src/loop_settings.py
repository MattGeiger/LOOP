#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""The settings people can change, in one place, for the setup wizard and the Settings window.

FIELDS lists every setting: where it is kept (profile.json for the organization's identity and look, site.json
for this deployment's private settings), its label and help text, and how it is checked. Both front ends draw their
forms from it, check values with validate(), and save through build() and the privileged `settings` action, so the
wizard and Settings can never disagree.

  values = current()                    what is set now (a flat {key: value} dict)
  errors = validate(values)             {key: "what is wrong"}; empty when everything is fine
  profile, site = build(values)         the two files to install (only what differs from the base profile)
  theme_problems(theme)                 WCAG 2.2 contrast problems in a Staff Display Tools theme

  python3 loop_settings.py check DIR    (root, before installing) check DIR's profile.json, site.json and pictures
"""
import copy
import json
import math
import os
import re
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_profile  # noqa: E402

PAGES = [
    ("organization", "Organization", "Who the displays belong to and who staff contact for help."),
    ("library", "Video library", "Where staff download the approved videos for the displays."),
    ("display", "This display", "How this TV is mounted. The Pi's own picture always stays landscape; "
                                "videos and the idle screen are turned to suit the TV."),
    ("pictures", "Pictures", "The logo, the Staff Tools icon and the idle screen. Leave a picture unchanged to keep "
                             "the current one."),
    ("colors", "Colors", "Every color is checked for readable contrast (WCAG 2.2) before it can be saved."),
]

ROTATE_CHOICES = [(0, "Landscape (normal)"), (90, "On its side, turned clockwise (top of the picture on the "
                                                    "right)"), (180, "Upside down"),
                  (270, "On its side, turned anticlockwise (top of the picture on the left)")]
ROTATE_ORIENTATION = {0: "landscape", 90: "portrait-cw", 180: "landscape-flipped", 270: "portrait-ccw"}

# key, page, kind, label, help, where ("profile" | "site" | "display" | "file"), options
FIELDS = [
    ("identity.organization", "organization", "text", "Organization name",
     "Shown in About. Leave empty to show none.", "profile", {"max": 80}),
    ("identity.website", "organization", "url", "Website", "Optional.", "profile", {}),
    ("identity.displays_name", "organization", "text", "What staff call the screens",
     'Used in Help, for example "the lobby displays".', "profile", {"required": True, "max": 60}),
    ("identity.contact", "organization", "text", "Who staff contact for help",
     'For example "the front desk manager" or a phone number.', "site", {"required": True, "max": 80}),
    ("identity.launcher_name", "organization", "text", "Desktop icon name",
     "The label under the Staff Tools icon.", "profile", {"required": True, "max": 24}),
    ("content.library_url", "library", "url", "Video library link",
     "The web page or shared folder where staff download approved videos. https only.",
     "site", {"required": True, "https": True}),
    ("content.library_name", "library", "text", "Video library name",
     'What staff call it, for example "Marketing videos".', "profile", {"required": True, "max": 60}),
    ("content.bookmark_name", "library", "text", "Bookmark name", "The browser bookmark's label.", "profile",
     {"required": True, "max": 60}),
    ("content.keep_videos", "library", "int", "Videos kept on the display",
     "Older videos beyond this number are removed automatically.", "profile", {"min": 1, "max": 20}),
    ("display.label", "display", "text", "Display name", 'For example "Lobby" or "Front window".', "display",
     {"required": True, "max": 40}),
    ("display.rotate", "display", "rotate", "How the TV is mounted",
     "Videos for a TV on its side must be made already turned this way (pre-rotated). The idle screen is "
     "turned for you.", "display", {}),
    ("colors.desktop", "colors", "color", "Desktop color", "Desktop, window title bars and taskbar.",
     "profile", {"dark": True}),
    ("colors.accent", "colors", "color", "Highlight color", "Menu and selection highlight (white text).",
     "profile", {}),
    ("theme.accent", "colors", "color", "Button color",
     "Buttons and messages. Must read well on the dark window.",
     "profile", {}),
    ("theme.bg_start", "colors", "color", "Background, top",
     "Staff Tools window, top left. Keep it dark.", "profile", {}),
    ("theme.bg_end", "colors", "color", "Background, bottom",
     "Bottom right; the window blends between the two.", "profile", {}),
    ("file.logo", "pictures", "image", "Header logo",
     "White or light logo on a transparent background, at least 720 pixels wide (PNG or SVG).", "file",
     {"name": "logo-white", "types": ("png", "svg")}),
    ("file.icon", "pictures", "image", "Staff Tools icon", "Square, at least 256 x 256 pixels (PNG).", "file",
     {"name": "staff-icon", "types": ("png",)}),
    ("file.idle", "pictures", "image", "Idle screen picture",
     "1920 x 1080 (PNG or JPG). Shown when no video is playing; played as a video to keep the Pi cool.", "file",
     {"name": "idle-screen", "types": ("png", "jpg")}),
    ("file.idle_portrait", "pictures", "image", "Idle screen for a TV on its side",
     "1080 x 1920 (PNG or JPG). Used instead of the one above when the TV is mounted on its side.", "file",
     {"name": "idle-screen-portrait", "types": ("png", "jpg")}),
]
FIELD = {f[0]: f for f in FIELDS}
SITE_KEYS = ("identity.contact", "content.library_url")
RESET_MARK = "reset-branding"  # in a settings folder: use the base profile's pictures (remove the ones added)
OWN_BRANDING = "/etc/loop/branding"


def own_pictures():
    """Pictures added in setup or Settings (they replace the profile's own)."""
    try:
        return sorted(f for f in os.listdir(OWN_BRANDING) if not f.startswith("."))
    except OSError:
        return []


# ------------------------------------------------------------------ colours and contrast (WCAG 2.2)
def _rgb(hx):
    return [int(hx[i:i + 2], 16) for i in (1, 3, 5)]


def _lum(hx):
    c = [v / 255 for v in _rgb(hx)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    hi, lo = sorted([_lum(a), _lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg, bg, alpha):
    f, b = _rgb(fg), _rgb(bg)
    return "#%02x%02x%02x" % tuple(round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3))


def is_color(v):
    return isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v) is not None


def theme_problems(t):
    """WCAG 2.2 problems in a theme: text 4.5:1 on every background it can sit on (1.4.3), borders and buttons
    3:1 on the window (1.4.11). Empty when it passes."""
    fails = []
    backgrounds = {k: t[k] for k in ("bg_start", "bg_mid", "bg_end", "surface", "card_bottom",
                                      "card_hover_top", "card_hover_bottom")}
    backgrounds["bg_mid+glow1"] = blend(t["glow1"], t["bg_mid"], 0.20)  # where the glows are strongest
    backgrounds["bg_end+glow2"] = blend(t["glow2"], t["bg_end"], 0.14)
    for fg in ("text", "text_muted", "text_soft", "text_body", "link", "ok", "danger", "accent"):
        worst, where = min((ratio(t[fg], b), n) for n, b in backgrounds.items())
        if worst < 4.5:
            fails.append(f"{fg} {t[fg]} is {worst:.2f}:1 on {where} (needs 4.5)")
    for bg in ("accent", "accent_deep"):
        r = ratio(t["on_accent"], t[bg])
        if r < 4.5:
            fails.append(f"on_accent {t['on_accent']} is {r:.2f}:1 on {bg} (needs 4.5)")
    for ui in ("border", "border_hover", "accent"):
        worst, where = min((ratio(t[ui], t[b]), b) for b in ("bg_start", "bg_mid", "bg_end"))
        if worst < 3.0:
            fails.append(f"{ui} {t[ui]} is {worst:.2f}:1 on {where} (needs 3 for components)")
    return fails


# ---- OKLCH (perceptual lightness, chroma, hue): shades of a color that keep its hue
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def to_oklch(hx):
    r, g, b = (_lin(v / 255) for v in _rgb(hx))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(a, bb), math.atan2(bb, a)


def from_oklch(L, C, h):
    """The sRGB hex for an OKLCH color, lowering chroma until it fits the screen's colors (hue kept)."""
    while True:
        a, bb = C * math.cos(h), C * math.sin(h)
        l_ = (L + 0.3963377774 * a + 0.2158037573 * bb) ** 3
        m_ = (L - 0.1055613458 * a - 0.0638541728 * bb) ** 3
        s_ = (L - 0.0894841775 * a - 1.2914855480 * bb) ** 3
        rgb = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
               -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
               -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
        if all(-0.0005 <= v <= 1.0005 for v in rgb) or C <= 0:
            return "#%02x%02x%02x" % tuple(round(255 * _gam(min(1.0, max(0.0, v)))) for v in rgb)
        C = max(0.0, C - 0.005)


def tinted_dark(color):
    """A very dark shade of a color's own hue: text that looks designed for the button, not plain black."""
    _L, C, h = to_oklch(color)
    return from_oklch(0.24, min(C, 0.07), h)


def button_theme(theme, accent):
    """The theme with a new button color: a slightly deeper shade for its gradient, and the button text that
    reads on both ends of it (WCAG 4.5:1), preferring a dark shade of the button's own hue, then the profile's,
    then white. If none passes, the best one is kept and validate() offers a readable shade of the color."""
    t = dict(theme, accent=accent.lower(), accent_deep=blend("#000000", accent, 0.10))
    choices = [tinted_dark(accent), theme.get("on_accent", "#131935"), theme.get("bg_start", "#0c111d"), "#ffffff"]
    worst = {c: min(ratio(c, t["accent"]), ratio(c, t["accent_deep"])) for c in choices}
    passing = [c for c in choices if worst[c] >= 4.5]
    t["on_accent"] = passing[0] if passing else max(choices, key=worst.get)
    return t


TEXT_KEYS = ("text", "text_muted", "text_soft", "text_body", "link", "ok", "danger", "border", "border_hover")


def gradient_theme(theme, top, bottom):
    """The theme with a two-tone window background: the middle, card and panel colors follow from the two."""
    mid = blend(top, bottom, 0.5)
    return dict(theme, bg_start=top.lower(), bg_end=bottom.lower(), bg_mid=mid,
                surface=blend("#ffffff", mid, 0.02), card_bottom=blend("#ffffff", mid, 0.07),
                card_hover_top=blend("#ffffff", mid, 0.04), card_hover_bottom=blend("#ffffff", mid, 0.10))


def full_theme(values, base=None):
    """The Staff Display Tools theme the values describe: the base profile's, with the chosen background and
    button colors applied only where they differ from it."""
    t = dict(base_config(base or values.get("base") or base_name())["theme"])
    top, bottom = values.get("theme.bg_start"), values.get("theme.bg_end")
    if is_color(top) and is_color(bottom) and (top.lower(), bottom.lower()) != (t["bg_start"], t["bg_end"]):
        t = gradient_theme(t, top, bottom)
    acc = values.get("theme.accent")
    if is_color(acc) and acc.lower() != t["accent"].lower():
        t = button_theme(t, acc)
    return t


def _background_ok(theme):
    return not [p for p in theme_problems(theme) if p.split(" ")[0] in TEXT_KEYS]


def _button_ok(theme, accent):
    return not [p for p in theme_problems(button_theme(theme, accent)) if p.startswith(("accent", "on_accent"))]


def _nearest(color, ok):
    """The closest shade of color (same hue, lightness stepped up and down in OKLCH) for which ok(hex) is true,
    or None."""
    L, C, h = to_oklch(color)
    for step in range(1, 201):  # the whole lightness range, nearest first
        for L2 in (L + step * 0.005, L - step * 0.005):
            if 0.0 <= L2 <= 1.0:
                cand = from_oklch(L2, C, h)
                if ok(cand):
                    return cand
    return None


def readable_suggestion(key, value, base=None, values=None):
    """For a color that fails its contrast check: the nearest readable shade, to offer as a one-click fix."""
    if not is_color(value):
        return None
    if key == "theme.accent":
        theme = full_theme(dict(values or {}, **{"theme.accent": None}), base) if values else \
            base_config(base or base_name())["theme"]
        return None if _button_ok(theme, value) else _nearest(value, lambda c: _button_ok(theme, c))
    if key in ("theme.bg_start", "theme.bg_end"):
        vals = dict(values or {})
        ref = base_config(base or vals.get("base") or base_name())["theme"]
        vals.setdefault("theme.bg_start", ref["bg_start"])
        vals.setdefault("theme.bg_end", ref["bg_end"])

        def ok(c):
            v = dict(vals, **{key: c, "theme.accent": None})
            return _background_ok(full_theme(v, base))
        return None if ok(value) else _nearest(value, ok)
    if key in ("colors.desktop", "colors.accent"):  # white text sits on both (desktop labels, menu highlight)
        good = lambda c: ratio(c, "#ffffff") >= 4.5  # noqa: E731
        return None if good(value) else _nearest(value, good)
    return None


# ------------------------------------------------------------------ reading and checking
def _get(d, dotted, default=None):
    for part in dotted.split("."):
        if not isinstance(d, dict) or part not in d:
            return default
        d = d[part]
    return d


def _set(d, dotted, value):
    parts = dotted.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def base_name():
    return loop_profile.get("basedOn", "") or "default"


def base_config(name):
    """DEFAULTS with a packaged profile on top (what a profile.json of {"basedOn": name} gives)."""
    merged = copy.deepcopy(loop_profile.DEFAULTS)
    d = loop_profile.base_profile_dir(name)
    if d and os.path.isfile(os.path.join(d, "profile.json")):
        try:
            loop_profile._merge(merged, json.load(open(os.path.join(d, "profile.json"))))
        except (OSError, ValueError):
            pass
    return merged


def packaged_profiles():
    names = set()
    for root in ("/usr/share/loop/profiles", os.path.join(loop_profile.CODE_DIR, "..", "profiles")):
        if os.path.isdir(root):
            names.update(n for n in os.listdir(root) if os.path.isfile(os.path.join(root, n, "profile.json")))
    return sorted(names, key=lambda n: (n != "default", n))


def current(hostname=None):
    """What is set now, as a flat {key: value} dict (pictures are not included: they are files)."""
    host = hostname or socket.gethostname()
    cfg = loop_profile.load()
    v = {k: _get(cfg, k) for k, *_ in FIELDS if not k.startswith(("display.", "file."))}
    disp = loop_profile.display(host)
    v["display.label"] = disp.get("label", host)
    v["display.rotate"] = disp["rotate"]
    v["base"] = base_name()
    return v


def validate(values):
    """{key: problem} for every value that is not acceptable."""
    errors = {}
    for key, _page, kind, label, _help, _where, opt in FIELDS:
        if kind == "image":
            path = values.get(key)
            if path:
                problem = picture_problem(path, opt["types"])
                if problem:
                    errors[key] = problem
            continue
        val = values.get(key)
        if kind in ("text", "url"):
            val = (val or "").strip()
            if opt.get("required") and not val:
                errors[key] = f"{label} is needed."
            elif len(val) > opt.get("max", 300):
                errors[key] = f"Keep it under {opt['max']} characters."
            elif any(ch in val for ch in "\n\r\t<>{}"):
                errors[key] = "Use plain text (no line breaks or < > { })."
            elif kind == "url" and val:
                ok = re.fullmatch(r"https://[^\s/$.?#][^\s]*" if opt.get("https") else r"https?://[^\s/$.?#][^\s]*",
                                  val)
                if not ok:
                    errors[key] = "Enter a full link starting with https://" if opt.get("https") else \
                        "Enter a full link starting with https:// (or leave it empty)."
        elif kind == "int":
            try:
                n = int(val)
                if not opt.get("min", n) <= n <= opt.get("max", n):
                    raise ValueError
            except (TypeError, ValueError):
                errors[key] = f"Enter a number from {opt.get('min')} to {opt.get('max')}."
        elif kind == "rotate":
            if val not in (0, 90, 180, 270):
                errors[key] = "Choose how the TV is mounted."
        elif kind == "color":
            if not is_color(val):
                errors[key] = "Enter a color like #1a2b3c."
    for key in ("theme.bg_start", "theme.bg_end"):
        if key not in errors and is_color(values.get(key)) and \
                not _background_ok(full_theme(dict(values, **{"theme.accent": None}))):
            fix = readable_suggestion(key, values[key], values.get("base"), values)
            if fix:
                errors[key] = f"Text would be hard to read on this background. Try {fix}, the nearest readable shade."
            elif key == "theme.bg_start":
                errors[key] = "Text would be hard to read on this background. Choose darker colors."
    if "theme.accent" not in errors and is_color(values.get("theme.accent")):
        theme = button_theme(full_theme(dict(values, **{"theme.accent": None})), values["theme.accent"])
        problems = [p for p in theme_problems(theme) if p.startswith(("accent", "on_accent"))]
        if problems:
            light = ratio(theme["accent"], theme["bg_start"]) < 4.5
            msg = ("Too dark to read on the window." if light else "Text cannot be read on this color.")
            fix = readable_suggestion("theme.accent", values["theme.accent"], values.get("base"))
            errors["theme.accent"] = msg + (f" Try {fix}, the nearest readable shade." if fix else
                                            " Choose a lighter or darker color.")
    for key, what in (("colors.desktop", "the desktop's white labels"), ("colors.accent", "white menu text")):
        if is_color(values.get(key)) and ratio(values[key], "#ffffff") < 4.5:
            fix = readable_suggestion(key, values[key])
            errors.setdefault(key, f"Too light for {what}." + (f" Try {fix}, the nearest readable shade." if fix
                                                               else " Choose a darker color."))
    return errors


PICTURE_MAGIC = {"png": [b"\x89PNG\r\n\x1a\n"], "jpg": [b"\xff\xd8\xff"]}


def picture_problem(path, types):
    """Why a picture file can't be used, or None. Never follows a symbolic link."""
    ext = os.path.splitext(path)[1].lower().lstrip(".").replace("jpeg", "jpg")
    if ext not in types:
        return "Use a " + " or ".join(t.upper() for t in types) + " file."
    if os.path.islink(path) or not os.path.isfile(path):
        return "That file can't be read."
    if os.path.getsize(path) > 20_000_000:
        return "That file is too large (over 20 MB)."
    head = open(path, "rb").read(512)
    if ext == "svg":
        if b"<svg" not in head and b"<?xml" not in head:
            return "That isn't an SVG picture."
    elif not any(head.startswith(m) for m in PICTURE_MAGIC[ext]):
        return f"That isn't a {ext.upper()} picture."
    return None


# ------------------------------------------------------------------ building the files
def build(values, existing_site=None, hostname=None):
    """(profile.json, site.json) dicts for the values. profile.json keeps only what differs from the base
    profile, so package upgrades still bring the base profile's improvements."""
    host = hostname or socket.gethostname()
    base = values.get("base") or base_name()
    ref = base_config(base)
    profile = {"schemaVersion": 1, "basedOn": base}
    site = copy.deepcopy(existing_site) if existing_site else {}
    for key, _page, kind, _label, _help, where, _opt in FIELDS:
        if kind == "image" or where == "display":
            continue
        val = values.get(key)
        if kind in ("text", "url"):
            val = (val or "").strip()
        elif kind == "int":
            val = int(val)
        elif kind == "color":
            val = val.lower()
        if key in ("theme.accent", "theme.bg_start", "theme.bg_end"):
            continue  # the theme is written as a whole below
        if where == "site":
            _set(site, key, val)
        elif val != (_get(ref, key).lower() if kind == "color" and is_color(_get(ref, key)) else _get(ref, key)):
            _set(profile, key, val)
    theme = full_theme(values, base)
    changed = {k: v for k, v in theme.items() if v != ref["theme"].get(k)}
    if changed:
        profile["theme"] = changed
    disp = site.setdefault("displays", {}).setdefault(host, {})
    disp["label"] = (values.get("display.label") or host).strip()
    disp["rotate"] = int(values.get("display.rotate") or 0)
    disp["orientation"] = ROTATE_ORIENTATION[disp["rotate"]]
    site.setdefault("system", {})
    return profile, site


def existing_site():
    for path in loop_profile._paths("site.json"):
        if os.path.isfile(path):
            try:
                return json.load(open(path))
            except (OSError, ValueError):
                return {}
    return {}


def check_dir(d):
    """Root's check of a settings folder written by the wizard or Settings (before anything is installed)."""
    problems = []
    for name in ("profile.json", "site.json"):
        p = os.path.join(d, name)
        if os.path.islink(p) or not os.path.isfile(p):
            problems.append(f"{name} is missing")
            continue
        try:
            data = json.load(open(p))
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            problems.append(f"{name} is not valid JSON")
    if problems:
        return problems
    profile, site = json.load(open(os.path.join(d, "profile.json"))), json.load(open(os.path.join(d, "site.json")))
    if profile.get("basedOn") and not loop_profile.base_profile_dir(profile["basedOn"]):
        problems.append(f"unknown base profile {profile['basedOn']}")
    merged = base_config(profile.get("basedOn") or "default")
    loop_profile._merge(merged, profile)
    loop_profile._merge(merged, site)
    values = {k: _get(merged, k) for k, *_ in FIELDS if not k.startswith(("display.", "file."))}
    disp = merged.get("displays", {}).get(socket.gethostname(), {})
    values.update({"display.label": disp.get("label", "display"), "display.rotate": disp.get("rotate", 0),
                   "base": profile.get("basedOn") or "default"})
    for key, *_rest, opt in FIELDS:
        if key.startswith("file."):
            for ext in opt["types"]:
                p = os.path.join(d, f"{opt['name']}.{ext}")
                if os.path.lexists(p):
                    values[key] = p
    problems += [f"{k}: {v}" for k, v in validate(values).items()]
    problems += [f"theme: {p}" for p in theme_problems(merged["theme"])]
    extra = [f for f in os.listdir(d) if f not in ("profile.json", "site.json", RESET_MARK) and
             os.path.splitext(f)[0] not in {o["name"] for *_x, o in FIELDS if "name" in o}]
    problems += [f"unexpected file {f}" for f in extra]
    return problems


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "check":
        found = check_dir(sys.argv[2])
        for p in found:
            print("loop-settings: " + p, file=sys.stderr)
        sys.exit(1 if found else 0)
    print(json.dumps(current(), indent=2))
