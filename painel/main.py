import logging
import os
import sys

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, Gtk

from . import style
from .http import UrllibClient
from .service import StatusService
from .tokens import TokenStore
from .window import Window

APP_ID = 'io.github.vina.Painel'
# action -> (accelerators, title shown in the shortcuts dialog)
ACCELS = {'win.add-repo': ['<Ctrl>t'], 'win.new-group': ['<Ctrl>n'], 'win.refresh': ['<Ctrl>r', 'F5'],
          'app.prefs': ['<Ctrl>comma'], 'app.shortcuts': ['<Ctrl>question'], 'app.quit': ['<Ctrl>q']}
SHORTCUTS = (('Repositories', (('Add repository', '<Ctrl>t'), ('Refresh', '<Ctrl>r F5'))),
             ('Groups', (('New group', '<Ctrl>n'),)),
             ('General', (('Preferences', '<Ctrl>comma'), ('Keyboard shortcuts', '<Ctrl>question'),
                          ('Quit', '<Ctrl>q'))))


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.settings = Gio.Settings.new(APP_ID)
        self.service, self.tokens = StatusService(UrllibClient()), TokenStore()
        self.menu = Gio.Menu()
        for items in ((('Preferences', 'app.prefs'), ('Keyboard Shortcuts', 'app.shortcuts')),
                      (('About Painel', 'app.about'), ('Quit', 'app.quit'))):
            section = Gio.Menu()
            for label, action in items:
                section.append(label, action)
            self.menu.append_section(None, section)
        for name, cb in (('prefs', lambda *_: self.props.active_window.show_prefs()),
                         ('shortcuts', self.shortcuts), ('about', self.about), ('quit', lambda *_: self.quit())):
            act = Gio.SimpleAction.new(name, None)
            act.connect('activate', cb)
            self.add_action(act)
        for action, accels in ACCELS.items():
            self.set_accels_for_action(action, accels)

    def do_startup(self):
        Adw.Application.do_startup(self)
        style.install()

    def do_activate(self):
        (self.props.active_window or Window(self, self.settings, self.service, self.tokens)).present()

    def shortcuts(self, *_):
        dialog = Adw.ShortcutsDialog()
        for title, items in SHORTCUTS:
            section = Adw.ShortcutsSection(title=title)
            for label, accel in items:
                section.add(Adw.ShortcutsItem.new(label, accel))
            dialog.add(section)
        dialog.present(self.props.active_window)

    def about(self, *_):
        Adw.AboutDialog(application_name='Painel', application_icon=APP_ID, version='0.1.0',
                        comments='Monitor GitHub and GitLab repositories',
                        developer_name='Vinicius Pedrinho', website='https://github.com/vinaooo/painel',
                        issue_url='https://github.com/vinaooo/painel/issues',
                        license_type=Gtk.License.MIT_X11).present(self.props.active_window)


def main():
    logging.basicConfig(level=logging.DEBUG if os.environ.get('PAINEL_DEBUG') else logging.WARNING)
    return App().run(sys.argv)
