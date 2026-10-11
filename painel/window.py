import threading

from gi.repository import Adw, GLib, Gtk

from . import repo_id
from .card import Card
from .prefs import Prefs

class Window(Adw.ApplicationWindow):
    def __init__(self, app, settings, service, tokens):
        super().__init__(application=app, title='Painel', default_width=800, default_height=600)
        self.settings, self.service, self.tokens = settings, service, tokens
        self.cards = {}
        self.timer = 0

        header = Adw.HeaderBar()
        add = Gtk.Button(icon_name='list-add-symbolic', tooltip_text='Add repository')
        add.connect('clicked', self.ask_repo)
        refresh = Gtk.Button(icon_name='view-refresh-symbolic', tooltip_text='Refresh')
        refresh.connect('clicked', lambda *_: self.refresh())
        header.pack_start(add)
        header.pack_start(refresh)
        menu = Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=app.menu)
        header.pack_end(menu)

        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START,
                                min_children_per_line=1, max_children_per_line=4,
                                homogeneous=True, margin_top=12, margin_bottom=12,
                                margin_start=12, margin_end=12)
        self.empty = Adw.StatusPage(title='No repositories', icon_name='io.github.vina.Painel-symbolic',
                                    description='Add a GitHub or GitLab URL with the + button.')
        self.stack = Gtk.Stack()
        self.stack.add_named(self.empty, 'empty')
        self.stack.add_named(Gtk.ScrolledWindow(child=self.flow), 'list')
        self.toasts = Adw.ToastOverlay(child=self.stack)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)

        repos = [repo_id.migrate(r) for r in settings.get_strv('repos')]
        settings.set_strv('repos', repos)
        for r in repos:
            self._add_card(r)
        self._sync_stack()
        self.refresh()
        self.restart_timer()
        settings.connect('changed::refresh-seconds', lambda *_: self.restart_timer())

    def restart_timer(self):
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add_seconds(self.settings.get_int('refresh-seconds'),
                                              lambda: self.refresh() or True)

    def _sync_stack(self):
        self.stack.set_visible_child_name('list' if self.cards else 'empty')

    def _add_card(self, name):
        card = Card(name, self.remove_repo)
        self.cards[name] = card
        self.flow.append(card)

    def ask_repo(self, *_):
        entry = Gtk.Entry(placeholder_text='GitHub/GitLab URL or owner/name',
                          activates_default=True)
        dlg = Adw.AlertDialog(heading='Add repository', extra_child=entry)
        dlg.add_response('cancel', 'Cancel')
        dlg.add_response('add', 'Add')
        dlg.set_response_appearance('add', Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response('add')
        dlg.connect('response', lambda d, r: r == 'add' and self.add_repo(entry.get_text()))
        dlg.present(self)

    def add_repo(self, text):
        name = repo_id.parse(text)
        if not name:
            self.toasts.add_toast(Adw.Toast(title='Invalid repository'))
            return
        if name.lower() in (k.lower() for k in self.cards):
            self.toasts.add_toast(Adw.Toast(title='Already added'))
            return
        self.settings.set_strv('repos', self.settings.get_strv('repos') + [name])
        self._add_card(name)
        self._sync_stack()
        self.refresh()

    def remove_repo(self, name):
        card = self.cards.pop(name)
        self.flow.remove(card.get_parent())
        self.settings.set_strv('repos', [r for r in self.settings.get_strv('repos') if r != name])
        self._sync_stack()

    def refresh(self):
        tokens = {}
        for name in list(self.cards):
            host = repo_id.host_of(name)
            if host not in tokens:
                tokens[host] = self.tokens.get(host)
            threading.Thread(target=self._worker, args=(name, tokens[host]), daemon=True).start()

    def _worker(self, name, token):
        data = self.service.fetch(name, token)
        GLib.idle_add(self._apply, name, data)

    def _apply(self, name, data):
        card = self.cards.get(name)  # may have been removed meanwhile
        if card:
            card.update(data)

    def show_prefs(self):
        Prefs(self.settings, self.tokens, self.cards).present(self)
