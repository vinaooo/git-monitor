"""Real sidebar group drag: drags the first group row below the third (see run.sh / group-dnd-test.sh), saves a
mid-drag screenshot to argv[1] if given and checks the stored group order."""
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
from painel.window import Window
from painel.status import RepoStatus
shot = sys.argv[1] if len(sys.argv) > 1 else None
Adw.init(); style.install()
sch = Gio.SettingsSchemaSource.new_from_directory(SCHEMAS, None, False)
s = Gio.Settings.new_full(sch.lookup('io.github.vina.Painel', False), Gio.memory_settings_backend_new(), None)
names = ['A', 'B', 'C', 'D']
s.set_value('groups', GLib.Variant('a(sas)', [(n, [f'gitlab.com/{n}/p']) for n in names]))
class T:
    def get(self, h): return None
class Svc:
    def wait(self, host): return 0
    def batch_size(self, host, token): return 0
    def not_modified_ratio(self): return 0.0
    def fetch(self, i, t, head=None): return RepoStatus(name=i, issues=0, prs=0, ci='none')
app = Adw.Application(); app.menu = Gio.Menu()
w = Window(app, s, Svc(), T()); w.fullscreen(); w.present()
ctx = GLib.MainContext.default()
def pump(sec=0.15):
    t0 = time.time()
    while time.time() - t0 < sec:
        while ctx.pending(): ctx.iteration(False)
        GLib.usleep(3000)
pump(1.5)
def center(i):
    ok, b = w.sidebar_slots[w.tab_view.get_nth_page(i)].compute_bounds(w)
    return b.get_x() + b.get_width() / 2, b.get_y() + b.get_height() / 2
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
(ax, ay), (cx, cy) = center(0), center(2)
print(f'variant=group A=({ax:.0f},{ay:.0f}) C=({cx:.0f},{cy:.0f})')
goto(ax, ay, 6); pump(0.3)
button(True)
goto(ax + 5, ay + 12, 4)
goto(cx, cy + 4, 20); pump(0.6)
r = w.reorder
print('during drag: dst =', r and r['dst'], ' offsets =', [round(sl.offset[1]) for sl in (r['slots'] if r else [])])
if shot:
    p = Gtk.WidgetPaintable.new(w); snap = Gtk.Snapshot()
    p.snapshot(snap, w.get_width(), w.get_height())
    w.get_renderer().render_texture(snap.to_node(), None).save_to_png(shot)
button(False); pump(0.8)
order = w.groups.names()
print('after drop : stored order =', order, ' sidebar =', [w.tab_view.get_nth_page(i).get_title() for i in range(4)],
      ' offsets =', [round(sl.offset[1]) for sl in w.sidebar_slots.values()])
ok = order == ['B', 'C', 'A', 'D']
print('RESULT', 'OK' if ok else 'NO-REORDER')
sess.call_sync('Stop', None, 0, -1, None)
sys.exit(0 if ok else 1)
