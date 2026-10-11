import threading

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from . import repo_id
from .card import Card
from .group_page import GroupPage
from .groups import Groups
from .motion import Slot
from .prefs import Prefs
from .titles import TitleStore


class Window(Adw.ApplicationWindow):
    def __init__(self, app, settings, service, tokens):
        super().__init__(application=app, title='Painel', default_width=900, default_height=600)
        self.settings, self.service, self.tokens = settings, service, tokens
        self.cards, self.pages, self.timer = {}, {}, 0
        self.titles = TitleStore(settings.get_value('titles').unpack(),
                                 lambda d: settings.set_value('titles', GLib.Variant('a{ss}', d)))
        initial = settings.get_value('groups').unpack()
        self.groups = Groups(initial, lambda g: settings.set_value('groups', GLib.Variant('a(sas)', g)),
                             legacy_repos=[repo_id.migrate(r) for r in settings.get_strv('repos')])
        if not initial:
            self.groups.persist()  # one-time migration of the old flat list

        self._build_ui(app)
        for group in self.groups.names():
            self._make_page(group)
            for repo in self.groups.repos(group):
                self._add_card(repo, group)
        self._apply_layout()
        self._update_actions()
        self.refresh()
        self.restart_timer()
        settings.connect('changed::refresh-seconds', lambda *_: self.restart_timer())
        settings.connect('changed::layout', lambda *_: self._apply_layout())

    # --- ui construction ---
    def _build_ui(self, app):
        header = Adw.HeaderBar()
        add = Gtk.Button(icon_name='list-add-symbolic', tooltip_text='Add repository')
        add.connect('clicked', self.ask_repo)
        refresh = Gtk.Button(icon_name='view-refresh-symbolic', tooltip_text='Refresh')
        refresh.connect('clicked', lambda *_: self.refresh())
        header.pack_start(add)
        header.pack_start(refresh)

        menu, section = Gio.Menu(), Gio.Menu()
        for label, action in (('New group…', 'new-group'), ('Rename group…', 'rename-group'),
                              ('Delete group…', 'delete-group')):
            section.append(label, f'win.{action}')
        menu.append_section(None, section)
        menu.append_section(None, app.menu)
        header.pack_end(Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=menu))
        self.actions = {}
        for name, cb in (('new-group', self.ask_new_group), ('rename-group', self.ask_rename_group),
                         ('delete-group', lambda *_: self.tab_view.close_page(self.tab_view.get_selected_page()))):
            act = Gio.SimpleAction.new(name, None)
            act.connect('activate', cb)
            self.add_action(act)
            self.actions[name] = act

        self.tab_view = Adw.TabView()
        self.tab_view.connect('close-page', self._on_close_page)
        self.tab_view.connect('page-reordered', lambda *_: self.groups.set_group_order(self._tab_order()))
        self.tab_view.connect('notify::selected-page', lambda *_: self._update_actions())
        self.tab_bar = Adw.TabBar(view=self.tab_view, autohide=False)
        new_tab = Gtk.Button(icon_name='tab-new-symbolic', tooltip_text='New group', css_classes=['flat'])
        new_tab.connect('clicked', self.ask_new_group)
        self.tab_bar.set_end_action_widget(new_tab)
        self.tab_bar.setup_extra_drop_target(Gdk.DragAction.MOVE, [GObject.TYPE_STRING])
        self.tab_bar.connect('extra-drag-drop', lambda _bar, page, ident: self._drop_on_page(page, ident))

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self.tab_bar)
        self.tab_view.set_vexpand(True)
        content.append(self.tab_view)
        self.split = Adw.OverlaySplitView(sidebar=Gtk.ScrolledWindow(child=self._build_sidebar()), content=content,
                                          show_sidebar=False, max_sidebar_width=240)
        self.toasts = Adw.ToastOverlay(child=self.split)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)

    def _build_sidebar(self):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, item):
            label = Gtk.Label(xalign=0, margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
            drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
            drop.connect('drop', lambda _t, ident, *_: self._drop_on_page(item.get_item(), ident))
            label.add_controller(drop)
            item.set_child(label)

        def bind(_f, item):
            item.binding = item.get_item().bind_property('title', item.get_child(), 'label',
                                                          GObject.BindingFlags.SYNC_CREATE)

        factory.connect('setup', setup)
        factory.connect('bind', bind)
        factory.connect('unbind', lambda _f, item: item.binding.unbind())
        lst = Gtk.ListView(model=self.tab_view.get_pages(), factory=factory)
        lst.add_css_class('navigation-sidebar')
        return lst

    def _apply_layout(self):
        sidebar = self.settings.get_string('layout') == 'sidebar'
        self.tab_bar.set_visible(not sidebar)
        self.split.set_show_sidebar(sidebar)

    # --- groups ---
    def _tab_order(self):
        return [self.tab_view.get_nth_page(i).get_child().name for i in range(self.tab_view.get_n_pages())]

    def _selected_group(self):
        return self.tab_view.get_selected_page().get_child().name

    def _tab_page(self, group):
        return self.tab_view.get_page(self.pages[group])

    def _update_actions(self):
        if self.tab_view.get_selected_page():
            can = self.groups.can_remove(self._selected_group())
            self.actions['delete-group'].set_enabled(can)
            self.actions['rename-group'].set_enabled(True)

    def _make_page(self, group):
        page = GroupPage(group, self.groups)
        self.pages[group] = page
        self.tab_view.append(page).set_title(group)
        return page

    def _ask_name(self, heading, label, initial, callback):
        entry = Gtk.Entry(text=initial, activates_default=True)
        dlg = Adw.AlertDialog(heading=heading, extra_child=entry)
        dlg.add_response('cancel', 'Cancel')
        dlg.add_response('ok', label)
        dlg.set_response_appearance('ok', Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response('ok')
        dlg.connect('response', lambda d, r: r == 'ok' and callback(entry.get_text()))
        dlg.present(self)

    def ask_new_group(self, *_):
        self._ask_name('New group', 'Create', '', self.new_group)

    def new_group(self, text):
        name = self.groups.add_group(text)
        if not name:
            self.toasts.add_toast(Adw.Toast(title='Invalid or duplicate group name'))
            return
        self.tab_view.set_selected_page(self._tab_page_of(self._make_page(name)))

    def _tab_page_of(self, page):
        return self.tab_view.get_page(page)

    def ask_rename_group(self, *_):
        old = self._selected_group()
        self._ask_name('Rename group', 'Rename', old, lambda text: self.rename_group(old, text))

    def rename_group(self, old, text):
        new = text.strip()
        if not self.groups.rename(old, new):
            if new != old:
                self.toasts.add_toast(Adw.Toast(title='Invalid or duplicate group name'))
            return
        page = self.pages.pop(old)
        page.name = new
        self.pages[new] = page
        self.tab_view.get_page(page).set_title(new)

    def _on_close_page(self, tab_view, tab_page):
        name = tab_page.get_child().name
        repos = self.groups.repos(name)
        if not self.groups.can_remove(name):
            tab_view.close_page_finish(tab_page, False)
        elif not repos:
            self._delete_group(tab_page)
        else:
            dlg = Adw.AlertDialog(heading=f'Delete “{name}”?',
                                  body=f'This stops monitoring its {len(repos)} repositories.')
            dlg.add_response('cancel', 'Cancel')
            dlg.add_response('delete', 'Delete')
            dlg.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.connect('response', lambda d, r: self._delete_group(tab_page) if r == 'delete'
                        else tab_view.close_page_finish(tab_page, False))
            dlg.present(self)
        return True

    def _delete_group(self, tab_page):
        name = tab_page.get_child().name
        for repo in self.groups.repos(name):
            self.remove_repo(repo)
        self.groups.remove(name)
        self.pages.pop(name)
        self.tab_view.close_page_finish(tab_page, True)

    # --- repos ---
    def _add_card(self, ident, group):
        card = Card(ident, self.remove_repo, self.rename_repo, self.drag_started, self.drag_finished,
                    self.titles.get(ident), other_groups=self.other_groups, on_move=self.move_to_group)
        self.cards[ident] = card
        self.pages[group].add_slot(ident, Slot(card))

    def ask_repo(self, *_):
        entry = Gtk.Entry(placeholder_text='GitHub/GitLab URL or owner/name', activates_default=True)
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
        group = self._selected_group()
        self.groups.add_repo(group, name)
        self._add_card(name, group)
        self.refresh()

    def rename_repo(self, name, title):
        self.titles.set(name, title)
        self.cards[name].set_custom_title(self.titles.get(name))

    def remove_repo(self, name):
        self.titles.remove(name)
        self.cards.pop(name)
        self.pages[self.groups.group_of(name)].remove_slot(name)
        self.groups.remove_repo(name)

    # --- moving between groups ---
    def other_groups(self, ident):
        return [g for g in self.groups.names() if g != self.groups.group_of(ident)]

    def _drop_on_page(self, tab_page, ident):
        self.move_to_group(ident, tab_page.get_child().name)
        return True

    def move_to_group(self, ident, group):
        GLib.idle_add(self._do_move, ident, group)  # after the drag finished: the source widget moves

    def _do_move(self, ident, group):
        old = self.groups.group_of(ident)
        if old is None or old == group or group not in self.pages:
            return
        slot = self.pages[old].remove_slot(ident)
        self.groups.move_repo(ident, group)
        self.pages[group].add_slot(ident, slot)
        self.toasts.add_toast(Adw.Toast(title=f'Moved to {group}'))

    # --- drag routing (a card may have changed group since its callbacks were bound) ---
    def drag_started(self, ident):
        self.pages[self.groups.group_of(ident)].drag_started(ident)

    def drag_finished(self, _ident):
        for page in self.pages.values():
            page.drag_finished()

    # --- refresh ---
    def restart_timer(self):
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add_seconds(self.settings.get_int('refresh-seconds'),
                                              lambda: self.refresh() or True)

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
        Prefs(self.settings, self.tokens, self.cards,
              lambda msg: self.toasts.add_toast(Adw.Toast(title=msg))).present(self)
