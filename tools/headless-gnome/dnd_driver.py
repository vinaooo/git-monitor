"""Real drag-and-drop test: drives Mutter's RemoteDesktop pointer API inside an isolated headless GNOME Shell
(see run.sh) and checks a card is reordered by dragging it over another card's chips.
Usage: dbus-run-session -- tools/headless-gnome/run.sh <outdir> tools/headless-gnome/dnd_driver.py [current|zero]"""
import subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SCHEMAS = tempfile.mkdtemp()
subprocess.run(['cp', str(ROOT / 'data/io.github.vina.Painel.gschema.xml'), SCHEMAS], check=True)
subprocess.run(['glib-compile-schemas', SCHEMAS], check=True)
import gi
gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); gi.require_version('Graphene', '1.0')
from gi.repository import Adw, Gio, GLib, Gtk
from painel import style
from painel.card import Card
from painel.window import Window
from painel.status import RepoStatus
variant = sys.argv[1] if len(sys.argv) > 1 else 'current'
Adw.init(); style.install()
sch = Gio.SettingsSchemaSource.new_from_directory(SCHEMAS, None, False)
s = Gio.Settings.new_full(sch.lookup('io.github.vina.Painel', False), Gio.memory_settings_backend_new(), None)
ids = [f'gitlab.com/g/p{i}' for i in range(6)]
s.set_value('groups', GLib.Variant('a(sas)', [('G', ids)]))
if variant == 'zero':      # old behaviour: hotspot (0, 0)
    def begin(self, source, ident, cb):
        source.set_icon(Gtk.WidgetPaintable.new(self).get_current_image(), 0, 0); self.set_opacity(0); cb(ident)
    Card._on_drag_begin = begin
class T:
    def get(self, h): return None
class Svc:
    def fetch(self, i, t):
        Z = dict(failure=0, running=0, cancelled=0, success=3); P = dict(changes=0, failing=0, conflict=0, waiting=4, approved=1, draft=0)
        return RepoStatus(name=i.split('/')[-1], issues=1, prs=5, ci='success', ci_counts=Z, pr_counts=P, url='https://github.com/o/r')
app = Adw.Application(); app.menu = Gio.Menu()
w = Window(app, s, Svc(), T()); w.fullscreen(); w.present()
ctx = GLib.MainContext.default()
def pump(sec=0.15):
    t0 = time.time()
    while time.time() - t0 < sec:
        while ctx.pending(): ctx.iteration(False)
        GLib.usleep(3000)
pump(1.5)
page = w.pages['G']
def center(i):
    ok, b = page.slots[i].get_parent().compute_bounds(w)
    return b.get_x() + b.get_width() / 2, b.get_y() + b.get_height() / 2, b.get_width(), b.get_height()
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
rd = Gio.DBusProxy.new_sync(bus, 0, None, 'org.gnome.Mutter.RemoteDesktop', '/org/gnome/Mutter/RemoteDesktop', 'org.gnome.Mutter.RemoteDesktop', None)
path = rd.call_sync('CreateSession', None, 0, -1, None).unpack()[0]
sess = Gio.DBusProxy.new_sync(bus, 0, None, 'org.gnome.Mutter.RemoteDesktop', path, 'org.gnome.Mutter.RemoteDesktop.Session', None)
sess.call_sync('Start', None, 0, -1, None)
pos = [0.0, 0.0]
def rel(dx, dy): sess.call_sync('NotifyPointerMotionRelative', GLib.Variant('(dd)', (dx, dy)), 0, -1, None)
def goto(x, y, steps=1):
    for k in range(1, steps + 1):
        tx, ty = pos[0] + (x - pos[0]) / (steps - k + 1), pos[1] + (y - pos[1]) / (steps - k + 1)
        rel(tx - pos[0], ty - pos[1]); pos[0], pos[1] = tx, ty; pump(0.02)
def button(down): sess.call_sync('NotifyPointerButton', GLib.Variant('(ib)', (0x110, bool(down))), 0, -1, None); pump(0.1)
rel(-4000, -4000); pos[:] = [0.0, 0.0]; pump(0.3)
ax, ay, cw, ch = center(ids[0]); cx, cy, _, _ = center(ids[2])
print(f'variant={variant} card size {cw:.0f}x{ch:.0f}  A=({ax:.0f},{ay:.0f}) C=({cx:.0f},{cy:.0f})')
pump(1.0)
goto(ax + 40, ay + 25, 6); pump(0.3)
button(True)
goto(ax + 60, ay + 30, 4)          # pass the drag threshold
goto(cx + 20, cy + 30, 25); pump(0.6)   # ends over the chips of card C
print('during drag: dragging =', page.dragging, ' flow order =', [i[-2:] for i in page._flow_order()], ' grab =', page.slots[ids[0]].card.grab_point)
button(False); pump(0.8)
print('after drop : stored order =', [i[-2:] for i in w.groups.repos('G')], ' flow =', [i[-2:] for i in page._flow_order()])
print('RESULT', 'OK' if w.groups.repos('G')[:3] != ids[:3] else 'NO-REORDER')
sess.call_sync('Stop', None, 0, -1, None)
sys.exit(0 if w.groups.repos('G')[:3] != ids[:3] else 1)
