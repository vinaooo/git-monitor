import logging
import os
import sys

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, GLib, Gtk

from . import background, repo_id, search_provider, signals, style
from .http import CachingClient, UrllibClient
from .service import StatusService
from .tokens import TokenStore
from .window import Window

APP_ID = 'io.github.vina.Painel'
# action -> (accelerators, title shown in the shortcuts dialog)
ACCELS = {'win.add-repo': ['<Ctrl>t'], 'win.new-group': ['<Ctrl>n'], 'win.refresh': ['<Ctrl>r', 'F5'], 'win.search': ['<Ctrl>f'],
          'app.prefs': ['<Ctrl>comma'], 'app.shortcuts': ['<Ctrl>question'], 'app.quit': ['<Ctrl>q']}
SHORTCUTS = (('Repositories', (('Add repository', '<Ctrl>t'), ('Refresh', '<Ctrl>r F5'), ('Search', '<Ctrl>f'))),
             ('Groups', (('New group', '<Ctrl>n'),)),
             ('General', (('Preferences', '<Ctrl>comma'), ('Keyboard shortcuts', '<Ctrl>question'),
                          ('Quit', '<Ctrl>q'))))


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.settings = Gio.Settings.new(APP_ID)
        repo_id.set_forgejo_hosts(self.settings.get_strv('forgejo-hosts'))
        self.service = StatusService(CachingClient(UrllibClient()), lambda: signals.enabled(self.settings))
        self.tokens = TokenStore()
        self.menu = Gio.Menu()
        for items in ((('Preferences', 'app.prefs'), ('Keyboard Shortcuts', 'app.shortcuts')),
                      (('About Git Monitor', 'app.about'), ('Quit', 'app.quit'))):
            section = Gio.Menu()
            for label, action in items:
                section.append(label, action)
            self.menu.append_section(None, section)
        for name, cb in (('prefs', lambda *_: self.window().show_prefs()),
                         ('shortcuts', self.shortcuts), ('about', self.about), ('quit', lambda *_: self.quit())):
            act = Gio.SimpleAction.new(name, None)
            act.connect('activate', cb)
            self.add_action(act)
        for name, cb in (('open-card', self.open_card), ('open-ci', self.open_ci)):
            act = Gio.SimpleAction.new(name, GLib.VariantType.new('s'))  # target: repo id / URL, set by CI notifications
            act.connect('activate', cb)
            self.add_action(act)
        for action, accels in ACCELS.items():
            self.set_accels_for_action(action, accels)
        self._held = False
        self.settings.connect('changed::run-in-background', lambda *_: self._sync_background(request=True))

    def do_startup(self):
        Adw.Application.do_startup(self)
        style.install()
        self._sync_background(request=self.settings.get_boolean('run-in-background'))

    def _sync_background(self, request):
        """Hold the app while 'run-in-background' is on, so closing the window only hides it."""
        on = self.settings.get_boolean('run-in-background')
        if on != self._held:
            self.hold() if on else self.release()
            self._held = on
        if request:
            background.request(on)

    def do_dbus_register(self, connection, object_path):
        if not Adw.Application.do_dbus_register(self, connection, object_path):
            return False
        search_provider.register(self, connection, self._search_items)
        return True

    def _search_items(self):
        win = (self.get_windows() or [None])[0]  # no window yet (service activation): nothing to search
        return [(i, c.title.get_label(), c.status) for i, c in win.cards.items()] if win else []

    def window(self):
        """The main window, created on first use; a hidden one is not `active_window`."""
        return (self.get_windows() or [None])[0] or Window(self, self.settings, self.service, self.tokens)

    def do_activate(self):
        self.window().present()

    def open_card(self, _action, target):
        self.activate()  # the app may have been started by the click
        win = self.window()
        if group := win.groups.group_of(target.get_string()):
            win.open_card(group, target.get_string())

    def open_ci(self, _action, target):
        Gtk.UriLauncher(uri=target.get_string()).launch(self.window(), None, None, None)

    def shortcuts(self, *_):
        dialog = Adw.ShortcutsDialog()
        for title, items in SHORTCUTS:
            section = Adw.ShortcutsSection(title=title)
            for label, accel in items:
                section.add(Adw.ShortcutsItem.new(label, accel))
            dialog.add(section)
        dialog.present(self.window())

    def about(self, *_):
        Adw.AboutDialog(application_name='Git Monitor', application_icon=APP_ID, version='0.1.0',
                        comments='Monitor GitHub, GitLab and Forgejo/Gitea repositories',
                        developer_name='Vinicius Pedrinho', website='https://github.com/vinaooo/git-monitor',
                        issue_url='https://github.com/vinaooo/git-monitor/issues',
                        license_type=Gtk.License.MIT_X11).present(self.window())


def main():
    logging.basicConfig(level=logging.DEBUG if os.environ.get('PAINEL_DEBUG') else logging.WARNING)
    return App().run(sys.argv)
