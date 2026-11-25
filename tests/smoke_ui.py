# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Matt Geiger, Temple Consulting, LLC.
"""Exercise Staff Tools and the admin windows with a fake GTK, to catch Python-level mistakes."""
import sys, types, os, tempfile
from unittest import mock
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")

class W:  # permissive fake widget
    _children = None
    def __init__(self, *a, **k): self._kids=[]; self._vis=True; self._active=False; self._val=0; self._text=""
    def __getattr__(self, n):
        if n.startswith("orig") or n.startswith("_"): raise AttributeError(n)
        return lambda *a, **k: W()
    def get_children(self): return list(self._kids)
    def pack_start(self, w, *a): self._kids.append(w)
    def pack_end(self, w, *a): self._kids.append(w)
    def add(self, w): self._kids.append(w); self._child=w
    def get_child(self): return getattr(self, "_child", W())
    def attach(self, w, *a): self._kids.append(w)
    def destroy(self): pass
    def connect(self, sig, cb, *a): self.__dict__.setdefault("_cb", {})[sig]=cb
    def set_visible(self, v): self._vis=v
    def get_active(self): return self._active
    def set_active(self, v): self._active=v
    def get_value(self): return self._val
    def set_value(self, v): self._val=v
    def get_text(self): return self._text
    def set_text(self, t): self._text=t
    def set_markup(self, t): self._text=t
    @classmethod
    def new_with_range(cls, *a): return cls()
    @classmethod
    def new_with_label(cls, *a): return cls()
    @classmethod
    def new_with_label_from_widget(cls, *a): return cls()
    @classmethod
    def new_from_file(cls, *a): return cls()
    @classmethod
    def new_from_pixbuf(cls, *a): return cls()
    @classmethod
    def list_toplevels(cls): return []

class GtkNS(types.SimpleNamespace):
    def __getattr__(self, n): return W
Gtk = GtkNS(Window=W, Box=W, Label=W, Button=W, Grid=W, Scale=W, SpinButton=W, CheckButton=W,
            RadioButton=W, ProgressBar=W, TextView=W, ScrolledWindow=W, Image=W, CssProvider=W, StyleContext=W,
            events_pending=lambda: False, main_iteration_do=lambda *a: None, main=lambda: None, main_quit=lambda *a: None)
for e in ("PolicyType","Justification","Orientation","PositionType","WindowPosition","ReliefStyle","WrapMode","Align"):
    setattr(Gtk, e, mock.MagicMock())
GLib = types.SimpleNamespace(Error=Exception, markup_escape_text=lambda t: t, timeout_add_seconds=lambda *a: 1,
                             timeout_add=lambda *a: 1, idle_add=lambda f, *a: f(*a))
gi = types.ModuleType("gi"); gi.require_version=lambda *a: None
repo = types.ModuleType("gi.repository"); repo.Gtk=Gtk; repo.GLib=GLib; repo.GdkPixbuf=mock.MagicMock(); repo.Gdk=mock.MagicMock(); repo.Pango=mock.MagicMock()
sys.modules.update({"gi": gi, "gi.repository": repo})
sys.path.insert(0, SRC)
import loop_state
tmp = tempfile.mkdtemp()
for k, v in dict(DATA=tmp, STATE=tmp+"/state", LOGS=tmp+"/logs").items(): setattr(loop_state, k, v)
loop_state.MODE_FILE=tmp+"/state/mode.json"; loop_state.BURNIN_FILE=tmp+"/state/burnin.json"; loop_state.MAINT_FILE=tmp+"/state/maint.json"
os.makedirs(tmp+"/logs")
FAKE = {"ro": True, "ssh": True}
loop_state.usb_ok=lambda: True; loop_state.helper_installed=lambda: True
loop_state.ro_now=lambda: FAKE["ro"]; loop_state.ro_next=lambda: FAKE["ro"]; loop_state.ssh_enabled=lambda: FAKE["ssh"]
BOOT=["b1"]; loop_state.boot_id=lambda: BOOT[0]
import staff_admin, staff_tools, threading
calls=[]
REPLY={}
def fake_root(args, on_done, on_line=None, log_path=None):
    calls.append(args[0]); rc, out = REPLY.get(args[0], (0, "ok"))
    if on_line: on_line(out)
    on_done(rc, out)
staff_admin.run_root = fake_root
staff_admin.helper_busy = lambda: False
class T:  # run threads inline
    def __init__(self, target, daemon=None): self.t=target
    def start(self): self.t()
staff_admin.threading.Thread = T
def press_all(win, label_hint=None):
    pass
main = staff_tools.StaffTools(); main.refresh()
print("main ok; banner text:", main.banner_text.get_text())
# --- update flow from read-only
u = staff_admin.UpdateWindow(main); print("intro", calls)
u.do_ro_off(); print("stage", loop_state.maint()["stage"])
u.do_restart(); BOOT[0]="b2"; FAKE["ro"]=False
u.show_current(); print("after boot:", loop_state.maint()["stage"], "held:", loop_state.video_held())
REPLY["check"]=(0, "system\t3\tlibc6 openssl overlayroot(new)\nvlc\t1\tvlc\nconnect\t0\t\nchromium\t0\t")
u.do_check(); print("found", u.found)
u.checks["vlc"]._active=True; u.do_install_selected(); print("stage", loop_state.maint()["stage"], calls[-1])
BOOT[0]="b3"; u.show_current(); print("post:", loop_state.maint()["stage"])
u.do_ro_on(); print("stage", loop_state.maint()["stage"])
BOOT[0]="b4"; FAKE["ro"]=True; print("after RO boot:", loop_state.maint(), "held", loop_state.video_held())
# failures
u.show_current(); REPLY["ro-off"]=(127,""); u.do_ro_off(); print("pw fail msg:", u.msg.get_text())
REPLY["ro-off"]=(0,"")
# interrupted install + escape hatch
loop_state.set_maint("installing", origin="ro"); BOOT[0]="b5"; FAKE["ro"]=False
u.show_current(); print("stage after power loss:", loop_state.maint()["stage"])
REPLY["check"]=(3, "ERROR: no internet"); u.do_repair(); print("repair->check msg:", u.msg.get_text())
btn=W(); btn._child=W(); u.do_escape(btn); u.do_escape(btn); print("escape held:", loop_state.video_held(), loop_state.maint().get("resume_without_ro"))
main.refresh(); print("warn:", main.warn.get_text())
loop_state.end_maint()
# install failure
REPLY["check"]=(0,"system\t2\ta b\nvlc\t0\t\nconnect\t0\t\nchromium\t0\t"); loop_state.set_maint("ready", origin="ro"); u.show_current(); u.do_check()
REPLY["update"]=(100,"E: dpkg was interrupted"); u.install(["all"]); print("after failed install:", loop_state.maint()["stage"], loop_state.maint()["note"])
loop_state.end_maint(); REPLY.pop("update")
# rw origin
FAKE["ro"]=False; u2=staff_admin.UpdateWindow(main); u2.do_start_rw(); print("rw stage", loop_state.maint())
REPLY["check"]=(0,"system\t0\t\nvlc\t0\t\nconnect\t0\t\nchromium\t0\t"); u2.do_check(); u2.do_finish_rw(); print("rw done", loop_state.maint())
# --- setup window
FAKE["ro"]=True
sw = staff_admin.SetupWindow(main); print("setup verdict:", sw.verdict.get_text())
sw.do_unlock(); print("unlocked", sw.unlocked)
sw.w_hours._val=2; sw.w_temp._val=85; sw.w_mem._val=80; sw.w_drop._val=0.002; sw.w_uptime._active=True; sw.w_ro._active=True
sw.do_start(); print("test:", loop_state.burnin()["test"]["state"], loop_state.burnin()["test"].get("ends"))
main.refresh(); print("banner:", main.banner_text.get_text())
btn=W(); btn._child=W(); sw.do_stop(btn); sw.do_stop(btn); print("after stop:", loop_state.burnin()["test"]["state"])
sw.unlocked=True; sw.show_current(); sw.w_hours._val=0; sw.w_ro._active=False; sw.w_temp._val=80; sw.w_mem._val=80; sw.w_drop._val=0.001
sw.do_start(); print("rw test pending:", loop_state.burnin()["test"]["state"], calls[-2:])
FAKE["ro"]=False; print("promote:", loop_state.promote_pending_test()["state"], "retention", loop_state.retention_hours())
# go live
calls.clear(); sw.p_golive(); sw.do_golive(); print("first golive click:", sw.msg.get_text()); sw.do_golive()
print("golive calls", calls, "mode", loop_state.mode(), "retention", loop_state.retention_hours())
print(staff_tools.status_text.__name__, "ok")
main.open_about(); print("about open:", main.about_win is not None); main.open_about()
import staff_tools as st; print(st.about_info()["facts"][0])

import staff_help as sh
gs = sh.load_guides(); print("guides:", [(g["slug"], len(g["blocks"])) for g in gs])
print("desc0:", gs[0]["description"][:70])
main.open_help(); hw = main.help_win
for i in range(len(gs)): hw.show_guide(i)
hw.show_index(); print("help ok", main.help_win is not None)
for g in gs:
    for k,t,x in g["blocks"]:
        if k=="img": print("  img", g["slug"], x)
