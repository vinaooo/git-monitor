from concurrent.futures import ThreadPoolExecutor

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from . import repo_id
from .card import Card
from .group_page import GroupPage
from .groups import Groups
from .health import group_severity, severity
from .motion import Slot
from .prefs import Prefs
from .status import RepoStatus
from .sorting import sorted_order
from .titles import TitleStore

# group marks, worst first: severity -> (icon, tooltip). A group shows one icon per kind present, side by side, in the
# sidebar row and over its tab; shapes differ so state never rests on colour alone. "success" = ready to merge / all green.
_MARKS = {'error': ('dialog-error-symbolic', 'Failing'),
          'warning': ('dialog-warning-symbolic', 'Needs attention'),
          'accent': ('emblem-synchronizing-symbolic', 'In progress'),
          'success': ('object-select-symbolic', 'Ready / all good')}


class Window(Adw.ApplicationWindow):
    def __init__(self, app, settings, service, tokens):
        super().__init__(application=app, title='Painel', width_request=360)
        self.settings, self.service, self.tokens = settings, service, tokens
        for key, prop in (('window-width', 'default-width'), ('window-height', 'default-height'),
                          ('window-maximized', 'maximized')):
            settings.bind(key, self, prop, Gio.SettingsBindFlags.DEFAULT)
        self.cards, self.pages, self.timer = {}, {}, 0
        self.pending, self.inflight, self.marks_scheduled = 0, set(), 0
        self.group_marks, self.sidebar_marks = {}, {}  # group name -> [severity]; TabPage -> its sidebar marks box
        self.tab_marks, self.tab_widgets = {}, {}  # TabPage -> marks box overlaid on the tab bar; TabPage -> its AdwTab
        self.pool = ThreadPoolExecutor(max_workers=4)  # ponytail: fixed 4 workers, make it a setting if hosts rate-limit
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
        self._apply_colors()
        self._apply_layout()
        self._apply_view()
        self._apply_sort()
        self._update_actions()
        self.refresh()
        self.tab_view.connect('notify::selected-page', lambda *_: self._on_group_focused())
        self.restart_timer()
        settings.connect('changed::refresh-seconds', lambda *_: self.restart_timer())
        settings.connect('changed::layout', lambda *_: (self._apply_layout(), self._update_marks()))
        settings.connect('changed::view', lambda *_: self._apply_view())
        for key in ('colored-tabs', 'colored-icons'):
            settings.connect(f'changed::{key}', lambda *_: self._apply_colors())
        settings.connect('changed::refresh-all-groups', lambda *_: self._update_marks())
        for key in ('sort', 'sort-reverse'):
            settings.connect(f'changed::{key}', lambda *_: self._apply_sort())

    # --- ui construction ---
    def _build_ui(self, app):
        menu, section = Gio.Menu(), Gio.Menu()
        for label, action in (('New group…', 'new-group'), ('Rename group…', 'rename-group'),
                              ('Delete group…', 'delete-group')):
            section.append(label, f'win.{action}')
        menu.append_section(None, section)
        for i in range(app.menu.get_n_items()):  # flatten: a section of sections loses its separators
            menu.append_section(None, app.menu.get_item_link(i, Gio.MENU_LINK_SECTION))
        self.actions = {}
        for name, cb in (('new-group', self.ask_new_group), ('rename-group', self.ask_rename_group),
                         ('delete-group', lambda *_: self.tab_view.close_page(self.tab_view.get_selected_page()))):
            act = Gio.SimpleAction.new(name, None)
            act.connect('activate', cb)
            self.add_action(act)
            self.actions[name] = act

        self.tab_view = Adw.TabView(vexpand=True)
        self.tab_view.connect('close-page', self._on_close_page)
        self.tab_view.connect('page-reordered', lambda *_: (self.groups.set_group_order(self._tab_order()),
                                                            GLib.idle_add(self._tint_tabs)))
        self.tab_view.connect('page-attached', lambda *_: GLib.idle_add(self._tint_tabs))  # tab widgets appear after this
        self.tab_view.connect('notify::selected-page', lambda *_: self._update_actions())
        group_menu = Gio.Menu()
        group_menu.append('Rename…', 'win.rename-group')
        group_menu.append('Delete…', 'win.delete-group')
        self.group_menu = group_menu
        self.tab_view.set_menu_model(group_menu)
        self.tab_view.connect('setup-menu', lambda _v, page: page and self.tab_view.set_selected_page(page))
        self.tab_bar = Adw.TabBar(view=self.tab_view, autohide=False)
        new_tab = Gtk.Button(icon_name='tab-new-symbolic', tooltip_text='New group', css_classes=['flat'])
        new_tab.connect('clicked', self.ask_new_group)
        self.tab_bar.set_end_action_widget(new_tab)
        self.tab_bar.setup_extra_drop_target(Gdk.DragAction.MOVE, [GObject.TYPE_VARIANT])
        self.tab_bar.connect('extra-drag-drop', lambda _bar, page, ident: self._drop_on_page(page, ident.unpack()))

        # content pane: own header bar (title = current group), like Files
        self.window_title = Adw.WindowTitle(title='Painel', subtitle='')
        content_header = Adw.HeaderBar(title_widget=self.window_title, show_start_title_buttons=False)
        act = Gio.SimpleAction.new('add-repo', None)
        act.connect('activate', self.ask_repo)
        self.add_action(act)
        add = Gtk.Button(icon_name='list-add-symbolic', tooltip_text='Add repository', action_name='win.add-repo')
        act = Gio.SimpleAction.new('refresh', None)
        act.connect('activate', lambda *_: self.refresh())
        self.add_action(act)
        self.refresh_button = refresh = Gtk.Button(icon_name='view-refresh-symbolic', tooltip_text='Refresh',
                                                   action_name='win.refresh')
        self.sidebar_toggle = Gtk.ToggleButton(icon_name='sidebar-show-symbolic', tooltip_text='Groups', visible=False)
        content_header.pack_start(self.sidebar_toggle)
        content_header.pack_start(add)
        content_header.pack_start(refresh)
        self.content_menu = Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=menu)  # tabs layout only
        content_header.pack_end(self.content_menu)
        self.view_button = Gtk.MenuButton(icon_name='view-grid-symbolic', always_show_arrow=True,
                                          tooltip_text='View and sort', menu_model=self._build_view_menu())
        content_header.pack_end(self.view_button)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # AdwTab holds one icon at most, so the marks are real icons overlaid on the bar and kept on their tab
        self.tab_overlay = Gtk.Overlay(child=self.tab_bar)
        self.tab_bar.add_tick_callback(lambda *_: self._place_tab_marks() or GLib.SOURCE_CONTINUE)
        content.append(self.tab_overlay)
        content.append(self.tab_view)
        content_view = Adw.ToolbarView(content=content)
        content_view.add_top_bar(content_header)
        self.toasts = Adw.ToastOverlay(child=content_view)

        # sidebar pane: runs the full window height, header bar included, like Files
        sidebar_header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title='Painel', subtitle=''),
                                       show_end_title_buttons=False)
        sidebar_header.pack_end(Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=menu))
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.append(Gtk.ScrolledWindow(child=self._build_sidebar(), vexpand=True))
        new_group = Gtk.Button(icon_name='list-add-symbolic', tooltip_text='New group', halign=Gtk.Align.END,
                               margin_top=6, margin_bottom=6, margin_end=6, css_classes=['flat'])
        new_group.connect('clicked', self.ask_new_group)
        sidebar.append(new_group)
        sidebar_view = Adw.ToolbarView(content=sidebar)
        sidebar_view.add_top_bar(sidebar_header)

        self.split = Adw.OverlaySplitView(sidebar=sidebar_view, content=self.toasts, show_sidebar=False,
                                          max_sidebar_width=260)
        self.set_content(self.split)

        # narrow window: the sidebar becomes an overlay opened by a header toggle
        breakpoint_ = Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 600sp'))
        breakpoint_.add_setter(self.split, 'collapsed', True)
        self.add_breakpoint(breakpoint_)
        self.sidebar_toggle.bind_property('active', self.split, 'show-sidebar',
                                          GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        self.split.connect('notify::collapsed', lambda *_: self._sync_toggle())

    def _build_view_menu(self):
        for key in ('sort', 'sort-reverse', 'view'):  # stateful actions backed by GSettings
            self.add_action(self.settings.create_action(key))
        menu = Gio.Menu()
        sort = Gio.Menu()
        for label, mode in (('Manual order', 'manual'), ('Name', 'name'), ('Open issues', 'issues'),
                            ('Pending PRs/MRs', 'prs'), ('Health (worst first)', 'ci')):
            sort.append(label, f'win.sort::{mode}')
        sort.append('Reverse order', 'win.sort-reverse')
        menu.append_section('Sort by', sort)
        view = Gio.Menu()
        for label, mode in (('Small cards', 'grid-small'), ('Medium cards', 'grid-medium'),
                            ('Large cards', 'grid-large'), ('List', 'list')):
            view.append(label, f'win.view::{mode}')
        menu.append_section('View', view)
        return menu

    def _build_sidebar(self):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, item):
            row = Gtk.Box(margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
            row.append(Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            row.append(Gtk.Box(spacing=4))  # group marks, filled by _update_marks: the tint alone would be colour-only
            drop = Gtk.DropTarget.new(GObject.TYPE_VARIANT, Gdk.DragAction.MOVE)
            drop.connect('drop', lambda _t, ident, *_: self._drop_on_page(item.get_item(), ident.unpack()))
            row.add_controller(drop)
            for gesture in (Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY), Gtk.GestureLongPress()):
                gesture.connect('pressed', lambda _g, *a: self._group_row_menu(item.get_item(), row, *a[-2:]))
                row.add_controller(gesture)
            item.set_child(row)

        def bind(_f, item):
            page, row = item.get_item(), item.get_child()
            marks = row.get_last_child()
            item.bindings = [page.bind_property('title', row.get_first_child(), 'label', GObject.BindingFlags.SYNC_CREATE)]
            self.sidebar_marks[page] = marks
            self._fill_marks(marks, self.group_marks.get(page.get_child().name, []))
            def tint(*_):
                if row.get_parent():  # the ListView row widget; not parented yet while binding
                    self._set_tint(row.get_parent(), page.get_keyword())

            item.tint_handler = page.connect('notify::keyword', tint)
            GLib.idle_add(tint)

        def unbind(_f, item):
            [b.unbind() for b in item.bindings]
            self.sidebar_marks.pop(item.get_item(), None)
            item.get_item().disconnect(item.tint_handler)

        factory.connect('setup', setup)
        factory.connect('bind', bind)
        factory.connect('unbind', unbind)
        lst = Gtk.ListView(model=self.tab_view.get_pages(), factory=factory)
        lst.add_css_class('navigation-sidebar')
        return lst

    def _group_row_menu(self, page, row, x, y):
        self.tab_view.set_selected_page(page)  # the group actions act on the selected group
        popover = Gtk.PopoverMenu.new_from_model(self.group_menu)
        popover.set_has_arrow(False)
        popover.set_halign(Gtk.Align.START)
        popover.set_parent(row)
        popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        popover.connect('closed', lambda p: GLib.idle_add(p.unparent))
        popover.popup()

    def _apply_layout(self):
        sidebar = self.settings.get_string('layout') == 'sidebar'
        self.tab_overlay.set_visible(not sidebar)
        self.content_menu.set_visible(not sidebar)  # the sidebar header carries the menu otherwise
        self._sync_toggle()

    def _sync_toggle(self):
        """Sidebar layout: pinned when wide, closed overlay behind a toggle when collapsed. Tabs layout: none."""
        sidebar, collapsed = self.settings.get_string('layout') == 'sidebar', self.split.get_collapsed()
        self.sidebar_toggle.set_visible(sidebar and collapsed)
        self.split.set_show_sidebar(sidebar and not collapsed)

    # --- view and sort (live: re-sorted whenever a refresh brings new numbers) ---
    def _apply_colors(self):
        for key in ('colored-tabs', 'colored-icons'):  # style.py scopes the colour rules under these window classes
            (self.add_css_class if self.settings.get_boolean(key) else self.remove_css_class)(key)

    def _apply_view(self):
        columns = {'grid-small': 6, 'grid-medium': 4, 'grid-large': 2, 'list': 1}
        mode = self.settings.get_string('view')
        self.view_button.set_icon_name('view-list-symbolic' if mode == 'list' else 'view-grid-symbolic')
        for page in self.pages.values():
            page.set_view(columns[mode], mode == 'list')

    def _apply_sort(self, group=None):
        mode, reverse = self.settings.get_string('sort'), self.settings.get_boolean('sort-reverse')
        for name in [group] if group else list(self.pages):
            order = [i for i in self.groups.repos(name) if i in self.cards]  # cards are created one by one at startup
            info = {i: (self.cards[i].title.get_label(), self.cards[i].status) for i in order}
            self.pages[name].apply_order(sorted_order(order, mode, reverse, info))

    # --- group health tint on the tab / sidebar row (only meaningful while every group is refreshed) ---
    _TINTS = ('tint-error', 'tint-warning', 'tint-accent', 'tint-success')

    @classmethod
    def _set_tint(cls, widget, sev):
        for css in cls._TINTS:
            widget.remove_css_class(css)
        if sev and sev != 'none':
            widget.add_css_class(f'tint-{sev}')

    @staticmethod
    def _fill_marks(box, marks):
        while child := box.get_first_child():
            box.remove(child)
        for sev in marks:
            icon, text = _MARKS[sev]
            image = Gtk.Image(icon_name=icon, tooltip_text=text, css_classes=[f'mark-{sev}'])
            image.update_property([Gtk.AccessibleProperty.LABEL], [text])
            box.append(image)

    def _update_marks(self):
        every = self.settings.get_boolean('refresh-all-groups')
        self.group_marks = {}
        for name, page in self.pages.items():
            cards = [self.cards[i] for i in self.groups.repos(name) if i in self.cards]
            sev = group_severity([severity(c.status) for c in cards]) if every else 'none'
            seen = {severity(c.status) for c in cards} if every else set()
            ready = any((c.status.pr_counts or {}).get('approved') for c in cards if c.status) if every else False
            marks = [m for m in ('error', 'warning', 'accent') if m in seen] + (['success'] if 'success' in seen or ready else [])
            self.group_marks[name] = marks
            tab = self.tab_view.get_page(page)
            tab.set_keyword(sev)  # carries the severity: sidebar rows follow its notify
            tab.set_tooltip(', '.join(_MARKS[m][1] for m in marks))
            if tab not in self.tab_marks:
                box = Gtk.Box(spacing=4, halign=Gtk.Align.START, valign=Gtk.Align.CENTER, can_target=False)
                self.tab_overlay.add_overlay(box)
                self.tab_marks[tab] = box
            self._fill_marks(self.tab_marks[tab], marks)
            if (box := self.sidebar_marks.get(tab)):
                self._fill_marks(box, marks)
        for tab in [t for t in self.tab_marks if t.get_child() is None or t.get_child().name not in self.pages]:
            self.tab_overlay.remove_overlay(self.tab_marks.pop(tab))
        self._tint_tabs()

    def _place_tab_marks(self):
        """Per frame while the tab bar is shown: park each marks box at the start of its tab (hidden if scrolled out)."""
        width = self.tab_overlay.get_width()
        for tab, box in self.tab_marks.items():
            ok, bounds = self.tab_widgets[tab].compute_bounds(self.tab_overlay) if tab in self.tab_widgets else (False, None)
            x = int(bounds.get_x()) + 8 if ok else 0
            visible = ok and x >= 0 and x + box.get_width() <= width and bool(box.get_first_child())
            if box.get_visible() != visible:
                box.set_visible(visible)
            if visible and box.get_margin_start() != x:
                box.set_margin_start(x)

    def _tint_tabs(self):
        """AdwTabBar has no per-tab API, so find its internal `tab` widgets and tag them by page."""
        def walk(widget):
            yield widget
            child = widget.get_first_child()
            while child:
                yield from walk(child)
                child = child.get_next_sibling()

        for widget in walk(self.tab_bar):
            if widget.get_css_name() == 'tab' and widget.find_property('page'):
                page = widget.get_property('page')
                if page:
                    self.tab_widgets[page] = widget
                    self._set_tint(widget, page.get_keyword())

    # --- groups ---
    def _tab_order(self):
        return [self.tab_view.get_nth_page(i).get_child().name for i in range(self.tab_view.get_n_pages())]

    def _selected_group(self):
        return self.tab_view.get_selected_page().get_child().name

    def _tab_page(self, group):
        return self.tab_view.get_page(self.pages[group])

    def _update_actions(self):
        if self.tab_view.get_selected_page():
            if self.split.get_collapsed():
                self.split.set_show_sidebar(False)  # picked a group from the overlay: get out of the way
            self.window_title.set_title(self._selected_group())
            can = self.groups.can_remove(self._selected_group())
            self.actions['delete-group'].set_enabled(can)
            self.actions['rename-group'].set_enabled(True)

    def _make_page(self, group):
        page = GroupPage(group, self.groups, can_reorder=lambda: self.settings.get_string('sort') == 'manual')
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
        self._update_marks()

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
            self._drop_repo(repo)  # the whole group was confirmed: no per-repo undo
        self.groups.remove(name)
        self.pages.pop(name)
        self.tab_view.close_page_finish(tab_page, True)

    # --- repos ---
    def _add_card(self, ident, group):
        card = Card(ident, self.remove_repo, self.rename_repo, self.drag_started, self.drag_finished,
                    self.titles.get(ident), other_groups=self.other_groups, on_move=self.move_to_group,
                    can_drag=lambda: self.settings.get_string('sort') == 'manual')
        self.cards[ident] = card
        self.pages[group].add_slot(ident, Slot(card))
        self._apply_sort(group)

    def ask_repo(self, *_):
        entry = Gtk.Entry(placeholder_text='GitHub/GitLab URL or owner/name', activates_default=True)
        dlg = Adw.AlertDialog(heading='Add repository', extra_child=entry)
        dlg.add_response('cancel', 'Cancel')
        dlg.add_response('add', 'Add')
        dlg.set_response_appearance('add', Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response('add')
        dlg.set_response_enabled('add', False)  # until the text parses as a repository

        def validate(_entry):
            text = entry.get_text()
            ok = bool(repo_id.parse(text))
            dlg.set_response_enabled('add', ok)
            (entry.remove_css_class if ok or not text.strip() else entry.add_css_class)('error')

        entry.connect('changed', validate)
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
        self._apply_sort(self.groups.group_of(name))

    def remove_repo(self, name):
        group, title = self.groups.group_of(name), self.titles.get(name)
        self._drop_repo(name)
        toast = Adw.Toast(title=f'Removed {name.rpartition("/")[2]}', button_label='Undo', timeout=8)
        toast.connect('button-clicked', lambda *_: self._restore_repo(name, group, title))
        self.toasts.add_toast(toast)

    def _restore_repo(self, name, group, title):
        if name in self.cards:
            return
        if group not in self.pages:  # its group was deleted meanwhile
            group = self._selected_group()
        self.groups.add_repo(group, name)  # appended: the old position is not kept
        if title:
            self.titles.set(name, title)
        self._add_card(name, group)
        self.refresh()

    def _drop_repo(self, name):
        self.titles.remove(name)
        self.cards.pop(name)
        self.pages[self.groups.group_of(name)].remove_slot(name)
        self.groups.remove_repo(name)
        self._update_marks()

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
        self._apply_sort(group)
        self._update_marks()
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

    def _on_group_focused(self):
        if not self.settings.get_boolean('refresh-all-groups'):  # otherwise it is already fresh
            self.refresh()  # new tab: refresh at once

    def refresh(self):
        if not self.tab_view.get_selected_page():
            return
        tokens = {}
        # default: only the visible group (saves API quota); the preference widens it to every group
        names = self.groups.all_repos() if self.settings.get_boolean('refresh-all-groups') \
            else self.groups.repos(self._selected_group())
        for name in names:
            host = repo_id.host_of(name)
            if host not in tokens:
                tokens[host] = self.tokens.get(host)
            if name in self.inflight:  # slow network: don't stack a second fetch on the same repo
                continue
            self.inflight.add(name)
            self.pending += 1
            self.pool.submit(self._worker, name, tokens[host])
        if self.pending:
            self.refresh_button.set_child(Gtk.Spinner(spinning=True))

    def _worker(self, name, token):
        try:
            data = self.service.fetch(name, token)
        except Exception as e:  # the service already maps failures; this keeps in-flight bookkeeping from leaking
            data = RepoStatus(name=name, error=str(e))
        GLib.idle_add(self._apply, name, data)

    def _apply(self, name, data):
        self.inflight.discard(name)
        self.pending -= 1
        if not self.pending:  # last result in: stop the spinner, stamp the time
            self.refresh_button.set_icon_name('view-refresh-symbolic')
            self.window_title.set_subtitle(f'Updated {GLib.DateTime.new_now_local().format("%H:%M")}')
        card = self.cards.get(name)  # may have been removed meanwhile
        if card:
            card.update(data)
            self._apply_sort(self.groups.group_of(name))
            if not self.marks_scheduled:  # a burst of results walks the tab bar once, not once per repo
                self.marks_scheduled = GLib.idle_add(self._flush_marks)

    def _flush_marks(self):
        self.marks_scheduled = 0
        self._update_marks()
        return GLib.SOURCE_REMOVE

    def show_prefs(self):
        Prefs(self.settings, self.tokens, self.cards,
              lambda msg: self.toasts.add_toast(Adw.Toast(title=msg)),
              active=self.groups.repos(self._selected_group())).present(self)  # for the rate-limit estimate
