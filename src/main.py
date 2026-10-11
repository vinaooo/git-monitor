import sys

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio

from .window import Window

APP_ID = 'io.github.vina.Painel'


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.settings = Gio.Settings.new(APP_ID)
        self.menu = Gio.Menu()
        self.menu.append('Preferences', 'app.prefs')
        self.menu.append('About Painel', 'app.about')
        for name, cb in (('prefs', lambda *_: self.props.active_window.show_prefs()),
                         ('about', self.about)):
            act = Gio.SimpleAction.new(name, None)
            act.connect('activate', cb)
            self.add_action(act)

    def do_activate(self):
        (self.props.active_window or Window(self, self.settings)).present()

    def about(self, *_):
        Adw.AboutDialog(application_name='Painel', application_icon=APP_ID, version='0.1.0',
                        comments='Monitor GitHub repositories',
                        license_type=3).present(self.props.active_window)  # 3 = GPL_3_0


def main():
    return App().run(sys.argv)
