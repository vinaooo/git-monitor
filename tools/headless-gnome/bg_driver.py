"""Integration test of 'run in background' + the Shell search provider, in an isolated headless session (see run.sh).
Runs the real App; the search provider is queried over D-Bus with gdbus (in a thread: the app must keep serving)."""
import json, os, subprocess, sys, tempfile, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TMP = tempfile.mkdtemp()
os.environ.update(GSETTINGS_SCHEMA_DIR=TMP, GSETTINGS_BACKEND='keyfile', XDG_CONFIG_HOME=TMP, XDG_DATA_HOME=TMP)
subprocess.run(['cp', str(ROOT / 'data/io.github.vina.Painel.gschema.xml'), TMP], check=True)
subprocess.run(['glib-compile-schemas', TMP], check=True)
import gi
gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')
from gi.repository import Gio, GLib
from painel.main import APP_ID, App

PATH = '/io/github/vina/Painel/SearchProvider'
IFACE = 'org.gnome.Shell.SearchProvider2'
settings = Gio.Settings.new(APP_ID)
settings.set_value('groups', GLib.Variant('a(sas)', [('G', ['github.com/o/r'])]))
app = App()
fails, step = [], {}


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name, detail)
    if not ok:
        fails.append(name)


def gdbus(method, *args):
    out = subprocess.run(['gdbus', 'call', '--session', '-d', APP_ID, '-o', PATH, '-m', f'{IFACE}.{method}', *args],
                         capture_output=True, text=True, timeout=20)
    return out.stdout.strip() + out.stderr.strip()


def in_thread(fn, then):
    def run():
        res = fn()
        GLib.idle_add(then, res)
    threading.Thread(target=run, daemon=True).start()


def win():
    return app.get_windows()[0] if app.get_windows() else None


def s1():  # window up, pref on -> held
    settings.set_boolean('run-in-background', True)
    check('app held when pref on', app._held)
    in_thread(lambda: gdbus('GetInitialResultSet', "['painel', 'github']"), s2)


def s2(res):
    check('search finds the card (window open)', 'github.com/o/r' in res, res)
    in_thread(lambda: gdbus('GetResultMetas', "['github.com/o/r']"), s3)


def s3(res):
    check('result meta has name/description', "'name'" in res and "'description'" in res, res)
    in_thread(lambda: gdbus('GetInitialResultSet', "['nomatch']"), s3b)


def s3b(res):
    check('non-matching query is empty', 'github.com/o/r' not in res, res)
    win().close()
    GLib.timeout_add(500, s4)


def s4():  # closed with pref on -> hidden, app alive
    w = win()
    check('window hidden, not destroyed', w is not None and not w.get_visible())
    in_thread(lambda: gdbus('GetInitialResultSet', "['painel', 'github']"), s5)


def s5(res):
    check('search works with hidden window', 'github.com/o/r' in res, res)
    in_thread(lambda: gdbus('ActivateResult', "'github.com/o/r'", "['x']", '0'), s6)


def s6(res):
    GLib.timeout_add(500, s7)


def s7():
    check('ActivateResult shows the window again', win().get_visible())
    settings.set_boolean('run-in-background', False)
    check('app released when pref off', not app._held)
    win().close()  # pref off: must quit
    GLib.timeout_add(500, lambda: GLib.SOURCE_REMOVE)


GLib.timeout_add_seconds(3, lambda: s1() or GLib.SOURCE_REMOVE)
GLib.timeout_add_seconds(40, lambda: (check('quit within timeout', False), app.quit()) and GLib.SOURCE_REMOVE)
app.run([])
check('app quit after close with pref off', win() is None)
print('RESULT', 'OK' if not fails else 'FAIL ' + ','.join(fails))
sys.exit(1 if fails else 0)
