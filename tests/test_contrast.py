# SPDX-License-Identifier: AGPL-3.0-or-later
"""WCAG 2.2 checks for every Staff Display Tools theme (LOOP's default and each profile under profiles/):

  1.4.3  text contrast at least 4.5:1 on every background it can sit on (text here is under 18 pt,
         so the large-text 3:1 allowance is not used)
  1.4.11 borders and button fills at least 3:1 against the window background
  readability: every font size in the style sheets is at least 11 pt
  2.5.8  small link-style buttons ask for a target of at least 24 x 24 px

Run: python3 tests/test_contrast.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import loop_profile  # noqa: E402


def rgb(hx):
    return [int(hx[i:i + 2], 16) for i in (1, 3, 5)]


def lum(hx):
    c = [v / 255 for v in rgb(hx)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg, bg, alpha):
    f, b = rgb(fg), rgb(bg)
    return "#%02x%02x%02x" % tuple(round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3))


def themes():
    base = loop_profile.DEFAULTS["theme"]
    yield "LOOP default (TemplePDX)", dict(base)
    for path in sorted(glob.glob(os.path.join(ROOT, "profiles", "*", "profile.json"))):
        t = dict(base)
        t.update(json.load(open(path)).get("theme", {}))
        yield os.path.basename(os.path.dirname(path)), t


def check_theme(name, t):
    fails = []
    backgrounds = {k: t[k] for k in ("bg_start", "bg_mid", "bg_end", "surface", "card_bottom",
                                      "card_hover_top", "card_hover_bottom")}
    backgrounds["bg_mid+glow1"] = blend(t["glow1"], t["bg_mid"], 0.20)      # where the glows are strongest
    backgrounds["bg_end+glow2"] = blend(t["glow2"], t["bg_end"], 0.14)
    for fg in ("text", "text_muted", "text_soft", "text_body", "link", "ok", "danger", "accent"):
        worst, where = min((ratio(t[fg], b), n) for n, b in backgrounds.items())
        if worst < 4.5:
            fails.append(f"{fg} {t[fg]} is {worst:.2f}:1 on {where} (needs 4.5)")
    for bg in ("accent", "accent_deep"):  # text on the main buttons and the busy (yellow) cards
        r = ratio(t["on_accent"], t[bg])
        if r < 4.5:
            fails.append(f"on_accent {t['on_accent']} is {r:.2f}:1 on {bg} (needs 4.5)")
    window = {k: t[k] for k in ("bg_start", "bg_mid", "bg_end")}
    for ui in ("border", "border_hover", "accent"):
        worst, where = min((ratio(t[ui], b), n) for n, b in window.items())
        if worst < 3.0:
            fails.append(f"{ui} {t[ui]} is {worst:.2f}:1 on {where} (needs 3 for components)")
    return fails


def check_styles():
    fails = []
    css = ""
    for f in ("staff_tools.py", "staff_admin.py", "staff_help.py", "settings_ui.py"):
        s = open(os.path.join(ROOT, "src", f)).read()
        css += "".join(re.findall(r'_?CSS = b"""(.*?)"""', s, re.S))
    for size in re.findall(r"font-size: (\d+(?:\.\d+)?)pt", css):
        if float(size) < 11:
            fails.append(f"font-size {size}pt is below 11 pt")
    rules = re.findall(r"([^{}]+)\{([^}]*)\}", css)
    for cls in ("about-link", "about-x", "link-btn", "help-toc", "help-back", "help-link", "tab", "choose", "color", "version-link"):
        sized = any(re.search(r"button\.%s\b" % cls, sel) and "min-height: 24px" in body for sel, body in rules)
        if not sized:
            fails.append(f"button.{cls} has no 24 px minimum target")
    return fails


ok = True
for name, theme in themes():
    fails = check_theme(name, theme)
    print(("ok   " if not fails else "FAIL ") + name + ("" if not fails else ":\n  " + "\n  ".join(fails)))
    ok &= not fails
style_fails = check_styles()
print(("ok   " if not style_fails else "FAIL ") + "text sizes and target sizes" +
      ("" if not style_fails else ":\n  " + "\n  ".join(style_fails)))
sys.exit(0 if ok and not style_fails else 1)
