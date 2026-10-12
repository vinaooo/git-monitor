from concurrent.futures import ThreadPoolExecutor

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from . import repo_id
from .card import Card
from .chips import chips_for
from .group_page import GroupPage
from . import importer
from .groups import Groups
from .group_settings import GroupSettingsDialog
from .health import group_severity, severity
from .import_dialog import ImportDialog
from .interval_row import IntervalRows
from .icon_picker import IconPicker
from .icons import DEFAULT as DEFAULT_ICON, IconStore
from .intervals import IntervalStore
from .motion import Slot
from .prefs import Prefs
from .search import matches
from .status import RepoStatus
from .sorting import sorted_order
from .virtual import DEFINITIONS, members, shown
from .sources import SourceStore
from .titles import TitleStore

# group marks, worst first: severity -> (icon, tooltip). A group shows one icon per kind present, side by side, in the
# sidebar row and over its tab; shapes differ so state never rests on colour alone. "success" = ready to merge / all green.
_MARKS = {'error': ('dialog-error-symbolic', 'Failing'),
          'warning': ('dialog-warning-symbolic', 'Needs attention'),
          'accent': ('emblem-synchronizing-symbolic', 'In progress'),
          'success': ('object-select-symbolic', 'Ready / all good')}

SYNC_SECONDS = 1800  # how often imported accounts are re-listed


class Window(Adw.ApplicationWindow):
    def __init__(self, app, settings, service, tokens):
        super().__init__(application=app, title='Painel', width_request=360)
        self.settings, self.service, self.tokens = settings, service, tokens
        for key, prop in (('window-width', 'default-width'), ('window-height', 'default-height'),
                          ('window-maximized', 'maximized')):
            settings.bind(key, self, prop, Gio.SettingsBindFlags.DEFAULT)
        self.query, self.results_scheduled = '', 0
        self.vpages, self.mirrors, self.virtual_active, self.virtual_scheduled = {}, {}, False, 0  # virtual groups
        self.cards, self.pages, self.timers = {}, {}, []  # timers: one refresh source per group
        self.pending, self.inflight, self.marks_scheduled = 0, set(), 0
        self.group_marks, self.sidebar_marks = {}, {}  # group name -> [severity]; TabPage -> its sidebar marks box
        self.pool = ThreadPoolExecutor(max_workers=4)  # ponytail: fixed 4 workers, make it a setting if hosts rate-limit
        self.titles = TitleStore(settings.get_value('titles').unpack(),
                                 lambda d: settings.set_value('titles', GLib.Variant('a{ss}', d)))
        self.sources = SourceStore(settings.get_value('sources').unpack(),
                                   lambda s: settings.set_value('sources', GLib.Variant('a(sssasas)', s)))
        self.icons = IconStore(settings.get_value('group-icons').unpack(),
                               lambda d: settings.set_value('group-icons', GLib.Variant('a{ss}', d)))
        self.sidebar_icons = {}  # TabPage -> its sidebar icon
        self.intervals = IntervalStore(settings.get_value('group-intervals').unpack(),
                                       lambda d: settings.set_value('group-intervals', GLib.Variant('a{si}', d)))
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
        self._sync_toggle()
        self._apply_view()
        self._apply_sort()
        self._update_actions()
        self.refresh()
        self.tab_view.connect('notify::selected-page', lambda *_: self._on_group_focused())
        self.restart_timers()
        settings.connect('changed::refresh-seconds', lambda *_: self.restart_timers())
        settings.connect('changed::sync-imported', lambda *_: self._sync_sources())
        GLib.timeout_add_seconds(5, lambda: self._sync_sources() or GLib.SOURCE_REMOVE)  # not on the startup path
        GLib.timeout_add_seconds(SYNC_SECONDS, lambda: self._sync_sources() or GLib.SOURCE_CONTINUE)
        settings.connect('changed::view', lambda *_: self._apply_view())
        settings.connect('changed::virtual-disabled', lambda *_: self._schedule_virtual())
        for key in ('colored-tabs', 'colored-icons'):
            settings.connect(f'changed::{key}', lambda *_: self._apply_colors())
        settings.connect('changed::refresh-all-groups', lambda *_: self._update_marks())
        for key in ('sort', 'sort-reverse'):
            settings.connect(f'changed::{key}', lambda *_: self._apply_sort())

    # --- ui construction ---
    def _build_ui(self, app):
        menu, section = Gio.Menu(), Gio.Menu()
        for label, action in (('Rename group…', 'rename-group'), ('Group settings…', 'group-settings'),
                              ('Delete group…', 'delete-group')):
            section.append(label, f'win.{action}')
        menu.append_section(None, section)
        for i in range(app.menu.get_n_items()):  # flatten: a section of sections loses its separators
            menu.append_section(None, app.menu.get_item_link(i, Gio.MENU_LINK_SECTION))
        self.actions = {}
        for name, cb in (('new-group', self.ask_new_group), ('import-account', self.ask_import), ('group-settings', self.ask_group_settings),
                         ('rename-group', self.ask_rename_group),
                         ('delete-group', lambda *_: self.tab_view.close_page(self.tab_view.get_selected_page()))):
            act = Gio.SimpleAction.new(name, None)
            act.connect('activate', cb)
            self.add_action(act)
            self.actions[name] = act

        self.tab_view = Adw.TabView(vexpand=True)
        self.vtab_view = Adw.TabView(vexpand=True)  # virtual groups: model + content, never persisted
        self.tab_view.connect('close-page', self._on_close_page)
        self.tab_view.connect('page-reordered', lambda *_: self.groups.set_group_order(self._tab_order()))
        self.tab_view.connect('notify::selected-page', lambda *_: self._show_real())  # picking a group drills into it
        group_menu = Gio.Menu()
        group_menu.append('Rename…', 'win.rename-group')
        group_menu.append('Settings…', 'win.group-settings')
        group_menu.append('Delete…', 'win.delete-group')
        self.group_menu = group_menu

        # content pane: own header bar (title = current group), like Files
        self.window_title = Adw.WindowTitle(title='Painel', subtitle='')
        content_header = Adw.HeaderBar(title_widget=self.window_title, show_start_title_buttons=False)
        act = Gio.SimpleAction.new('add-repo', None)
        act.connect('activate', self.ask_repo)
        self.add_action(act)
        act = Gio.SimpleAction.new('search', None)
        act.connect('activate', lambda *_: self.search_button.set_active(not self.search_button.get_active()))
        self.add_action(act)
        self.search_button = Gtk.ToggleButton(icon_name='edit-find-symbolic', tooltip_text='Search (Ctrl+F)')
        self.search_entry = Gtk.SearchEntry(width_request=260, placeholder_text='Search name, URL, passing, waiting…')
        self.search_entry.connect('search-changed', self._on_search_changed)
        self.search_entry.connect('stop-search', lambda *_: self.search_button.set_active(False))  # Esc
        self.search_button.connect('toggled', self._on_search_toggled)
        self.search_revealer = Gtk.Revealer(child=self.search_entry, transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT,
                                            transition_duration=250)  # grows out of the magnifier
        add_menu = Gio.Menu()
        for label, action in (('Add repository…', 'add-repo'), ('New group…', 'new-group'),
                              ('Import from account…', 'import-account')):
            add_menu.append(label, f'win.{action}')
        add = Gtk.MenuButton(icon_name='list-add-symbolic', tooltip_text='Add', menu_model=add_menu)
        act = Gio.SimpleAction.new('refresh', None)
        act.connect('activate', lambda *_: self.refresh())
        self.add_action(act)
        self.refresh_button = refresh = Gtk.Button(icon_name='view-refresh-symbolic', tooltip_text='Refresh',
                                                   action_name='win.refresh')
        self.sidebar_toggle = Gtk.ToggleButton(icon_name='sidebar-show-symbolic', tooltip_text='Groups', visible=False)
        content_header.pack_start(self.sidebar_toggle)
        content_header.pack_start(add)
        content_header.pack_start(refresh)
        content_header.pack_start(self.search_button)
        content_header.pack_start(self.search_revealer)
        self.view_button = Gtk.MenuButton(icon_name='view-grid-symbolic', always_show_arrow=True,
                                          tooltip_text='View and sort', menu_model=self._build_view_menu())
        content_header.pack_end(self.view_button)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=['boxed-list'], valign=Gtk.Align.START)
        self.results.set_placeholder(Adw.StatusPage(title='No Matches', icon_name='edit-find-symbolic',
                                                    description='No repository matches the search.'))
        self.results.connect('row-activated', self._open_result)
        clamp = Adw.Clamp(child=self.results, maximum_size=760, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.body = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)  # groups | search results
        self.body.add_named(self.tab_view, 'groups')
        self.body.add_named(self.vtab_view, 'virtual')
        self.body.add_named(Gtk.ScrolledWindow(child=clamp), 'results')
        content.append(self.body)
        content_view = Adw.ToolbarView(content=content)
        content_view.add_top_bar(content_header)
        self.toasts = Adw.ToastOverlay(child=content_view)

        # sidebar pane: runs the full window height, header bar included, like Files
        sidebar_header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title='Painel', subtitle=''),
                                       show_end_title_buttons=False)
        sidebar_header.pack_end(Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=menu))
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.real_list = self._build_sidebar()
        sidebar.append(Gtk.ScrolledWindow(child=self.real_list, vexpand=True))
        self.virtual_list = self._build_virtual_sidebar()
        # virtual groups sit at the bottom of the sidebar, under a separator
        self.virtual_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, visible=False)
        self.virtual_section.append(Gtk.Separator())
        self.virtual_section.append(Gtk.ScrolledWindow(child=self.virtual_list, propagate_natural_height=True,
                                                       max_content_height=300, hscrollbar_policy=Gtk.PolicyType.NEVER))
        sidebar.append(self.virtual_section)
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
            row = Gtk.Box(margin_top=10, margin_bottom=10, margin_start=12, margin_end=12, spacing=10)
            row.append(Gtk.Image())
            row.append(Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            row.append(Gtk.Box(spacing=4))  # group marks, filled by _update_marks: the tint alone would be colour-only
            drop = Gtk.DropTarget.new(GObject.TYPE_VARIANT, Gdk.DragAction.MOVE)
            drop.connect('drop', lambda _t, ident, *_: self._drop_on_page(item.get_item(), ident.unpack()))
            row.add_controller(drop)
            click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
            click.connect('released', lambda *_: self._show_real())  # also when the clicked row was already selected
            row.add_controller(click)
            for gesture in (Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY), Gtk.GestureLongPress()):
                gesture.connect('pressed', lambda _g, *a: self._group_row_menu(item.get_item(), row, *a[-2:]))
                row.add_controller(gesture)
            item.set_child(row)

        def bind(_f, item):
            page, row = item.get_item(), item.get_child()
            marks = row.get_last_child()
            icon = row.get_first_child()
            icon.set_from_icon_name(self.icons.get(page.get_child().name))
            self.sidebar_icons[page] = icon
            item.bindings = [page.bind_property('title', icon.get_next_sibling(), 'label', GObject.BindingFlags.SYNC_CREATE)]
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
            self.sidebar_icons.pop(item.get_item(), None)
            item.get_item().disconnect(item.tint_handler)

        factory.connect('setup', setup)
        factory.connect('bind', bind)
        factory.connect('unbind', unbind)
        lst = Gtk.ListView(model=self.tab_view.get_pages(), factory=factory)  # not single_click_activate: it also selects rows on hover
        lst.add_css_class('navigation-sidebar')
        return lst

    def _build_virtual_sidebar(self):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, item):
            row = Gtk.Box(margin_top=10, margin_bottom=10, margin_start=12, margin_end=12, spacing=10)
            row.append(Gtk.Image())
            row.append(Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END))
            click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
            click.connect('released', lambda *_: self._show_virtual())
            row.add_controller(click)
            item.set_child(row)

        def bind(_f, item):
            page, row = item.get_item(), item.get_child()
            row.get_first_child().set_from_icon_name(next(d.icon for d in DEFINITIONS if d.id == page.get_child().name))
            item.binding = page.bind_property('title', row.get_last_child(), 'label', GObject.BindingFlags.SYNC_CREATE)

        factory.connect('setup', setup)
        factory.connect('bind', bind)
        factory.connect('unbind', lambda _f, item: item.binding.unbind())
        lst = Gtk.ListView(model=self.vtab_view.get_pages(), factory=factory, css_classes=['navigation-sidebar', 'dim-selection'])
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

    def _sync_toggle(self):
        """Pinned sidebar when wide, closed overlay behind a header toggle when collapsed."""
        collapsed = self.split.get_collapsed()
        self.sidebar_toggle.set_visible(collapsed)
        self.split.set_show_sidebar(not collapsed)

    # --- view and sort (live: re-sorted whenever a refresh brings new numbers) ---
    def _apply_colors(self):
        for key in ('colored-tabs', 'colored-icons'):  # style.py scopes the colour rules under these window classes
            (self.add_css_class if self.settings.get_boolean(key) else self.remove_css_class)(key)

    def _apply_view(self):
        columns = {'grid-small': 6, 'grid-medium': 4, 'grid-large': 2, 'list': 1}
        mode = self.settings.get_string('view')
        self.view_button.set_icon_name('view-list-symbolic' if mode == 'list' else 'view-grid-symbolic')
        for page in [*self.pages.values(), *self.vpages.values()]:
            page.set_view(columns[mode], mode == 'list')

    def _apply_view_to(self, page):
        columns = {'grid-small': 6, 'grid-medium': 4, 'grid-large': 2, 'list': 1}
        mode = self.settings.get_string('view')
        page.set_view(columns[mode], mode == 'list')

    def _apply_sort(self, group=None):
        mode, reverse = self.settings.get_string('sort'), self.settings.get_boolean('sort-reverse')
        for name in [group] if group else list(self.pages):
            order = [i for i in self.groups.repos(name) if i in self.cards]  # cards are created one by one at startup
            info = {i: (self.cards[i].title.get_label(), self.cards[i].status) for i in order}
            self.pages[name].apply_order(sorted_order(order, mode, reverse, info))
        self._refilter(group)
        self._schedule_virtual()

    # --- search (all groups; the tab / sidebar title carries the match count) ---
    def _refilter(self, group=None):
        pred = self.query.strip() and (lambda c: matches(self.query, c.ident, c.title.get_label(), c.status))
        for name in [group] if group else list(self.pages):
            page = self.pages[name]
            page.set_filter(pred or None)
            self.tab_view.get_page(page).set_title(f'{name} ({page.match_count()})' if pred else name)
        if pred and not self.results_scheduled:  # debounced: a burst of refresh results rebuilds the list once
            self.results_scheduled = GLib.idle_add(self._fill_results)

    def _on_search_toggled(self, button):
        """The search box slides out of the magnifier; closing it clears the query."""
        on = button.get_active()
        self.search_revealer.set_reveal_child(on)
        if on:
            self.search_entry.grab_focus()
        else:
            self.search_entry.set_text('')
            self._show_body()

    def _on_search_changed(self, entry):
        self.query = entry.get_text()
        self._refilter()
        self._show_body()

    def _fill_results(self):
        """One list of every matching card across groups: title, group, and the same CI / PR words the card shows."""
        self.results_scheduled = 0
        while (row := self.results.get_first_child()):
            self.results.remove(row)
        if not self.query.strip():
            return GLib.SOURCE_REMOVE
        for group in self.pages:
            for ident in self.groups.repos(group):
                card = self.cards.get(ident)
                if not card or not matches(self.query, card.ident, card.title.get_label(), card.status):
                    continue
                row = Adw.ActionRow(title=GLib.markup_escape_text(card.title.get_label()), activatable=True,
                                    subtitle=GLib.markup_escape_text(f'{group} · {ident}'))
                row.group, row.ident = group, ident
                words = [c.text for _g, chips in chips_for(card.status) for c in chips]
                row.add_suffix(Gtk.Label(label=' · '.join(words), css_classes=['dim-label'], wrap=True, xalign=1,
                                         max_width_chars=34))
                self.results.append(row)
        return GLib.SOURCE_REMOVE

    def _open_result(self, _list, row):
        group, ident = row.group, row.ident
        self.tab_view.set_selected_page(self._tab_page(group))
        self._show_real()  # the card may be opened from a virtual group view
        self.search_button.set_active(False)  # closes the search, clears the query
        self.set_focus(None)

        def show():  # once the unfiltered grid has been laid out
            self.set_focus(None)  # else GTK parks keyboard focus on the first card and draws its focus ring
            if group in self.pages and ident in self.cards:
                self.pages[group].reveal(ident, lambda: ident in self.cards and self._blink(self.cards[ident]))  # blink once it has arrived
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(80, show)

    def _blink(self, card, ticks=6):
        """Flash the card's highlight: on/off three times."""
        if not card.get_parent() or ticks == 0:
            card.remove_css_class('search-hit')
            return
        (card.add_css_class if ticks % 2 == 0 else card.remove_css_class)('search-hit')
        GLib.timeout_add(220, lambda: self._blink(card, ticks - 1) or GLib.SOURCE_REMOVE)

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
            seen = {severity(c.status) for c in cards} if every else set()
            ready = any((c.status.pr_counts or {}).get('approved') for c in cards if c.status) if every else False
            seen.discard('success')  # green CI alone is not worth a mark: only a PR ready to merge is
            if ready:
                seen.add('success')
            sev = group_severity(seen)
            marks = [m for m in ('error', 'warning', 'accent', 'success') if m in seen]
            self.group_marks[name] = marks
            tab = self.tab_view.get_page(page)
            tab.set_keyword(sev)  # carries the severity: sidebar rows follow its notify
            tab.set_tooltip(', '.join(_MARKS[m][1] for m in marks))
            if (box := self.sidebar_marks.get(tab)):
                self._fill_marks(box, marks)

    # --- groups ---
    def _tab_order(self):
        return [self.tab_view.get_nth_page(i).get_child().name for i in range(self.tab_view.get_n_pages())]

    def _selected_group(self):
        return self.tab_view.get_selected_page().get_child().name

    def _tab_page(self, group):
        return self.tab_view.get_page(self.pages[group])

    def _update_actions(self):
        if self.split.get_collapsed():
            self.split.set_show_sidebar(False)  # picked a group from the overlay: get out of the way
        if self.virtual_active:
            self.window_title.set_title(next(d.title for d in DEFINITIONS if d.id == self._selected_vid()))
            for name in ('delete-group', 'rename-group', 'group-settings'):
                self.actions[name].set_enabled(False)  # a virtual group is read-only
        elif self.tab_view.get_selected_page():
            self.window_title.set_title(self._selected_group())
            can = self.groups.can_remove(self._selected_group())
            self.actions['delete-group'].set_enabled(can)
            self.actions['rename-group'].set_enabled(True)
            self.actions['group-settings'].set_enabled(True)

    def _show_body(self):
        self.body.set_visible_child_name('results' if self.query.strip() else 'virtual' if self.virtual_active else 'groups')

    def _show_real(self):
        self.virtual_active = False
        self.real_list.remove_css_class('dim-selection')  # only one sidebar row looks selected
        self.virtual_list.add_css_class('dim-selection')
        self._update_actions()
        self._show_body()

    def _show_virtual(self):
        if not self.vtab_view.get_selected_page():
            return
        self.virtual_active = True
        self.virtual_list.remove_css_class('dim-selection')
        self.real_list.add_css_class('dim-selection')
        self._update_actions()
        self._show_body()
        self.refresh()

    def _selected_vid(self):
        return self.vtab_view.get_selected_page().get_child().name

    # --- virtual groups: read-only collections of mirror cards across all groups ---
    def _schedule_virtual(self):
        if not self.virtual_scheduled:  # a burst of results rebuilds once
            self.virtual_scheduled = GLib.idle_add(self._sync_virtual)

    def _make_mirror(self, ident, page):
        card = Card(ident, self.remove_repo, self.rename_repo, lambda *_: None, lambda *_: None, self.titles.get(ident),
                    other_groups=self.other_groups, on_move=self.move_to_group, can_drag=lambda: False)
        if self.cards[ident].status:
            card.update(self.cards[ident].status)
        page.add_slot(ident, Slot(card))
        return card

    def _sync_virtual(self):
        self.virtual_scheduled = 0
        disabled = set(self.settings.get_strv('virtual-disabled'))
        items = [(i, self.cards[i].status) for g in self.groups.names() for i in self.groups.repos(g) if i in self.cards]
        by_id = {d.id: members(d, items) for d in DEFINITIONS}
        show = shown(disabled, by_id)
        mode, reverse = self.settings.get_string('sort'), self.settings.get_boolean('sort-reverse')
        for n, d in enumerate(DEFINITIONS):
            if d.id not in show:
                if d.id in self.vpages:
                    self.vtab_view.close_page(self.vtab_view.get_page(self.vpages.pop(d.id)))
                    self.mirrors.pop(d.id)
                continue
            if d.id not in self.vpages:
                page = GroupPage(d.id, self.groups, can_reorder=lambda: False)
                self.vpages[d.id], self.mirrors[d.id] = page, {}
                self.vtab_view.insert(page, sum(x.id in self.vpages for x in DEFINITIONS[:n]))
                self._apply_view_to(page)
            page, mirrors, want = self.vpages[d.id], self.mirrors[d.id], by_id[d.id]
            for ident in [i for i in mirrors if i not in want]:
                page.remove_slot(ident)
                del mirrors[ident]
            for ident in want:
                if ident not in mirrors:
                    mirrors[ident] = self._make_mirror(ident, page)
            info = {i: (mirrors[i].title.get_label(), self.cards[i].status) for i in want}
            page.apply_order(sorted_order(want, mode, reverse, info))
            self.vtab_view.get_page(page).set_title(f'{d.title} ({len(want)})')
        self.virtual_section.set_visible(bool(self.vpages))
        if self.virtual_active and not self.vtab_view.get_selected_page():
            self._show_real()  # the open virtual group disappeared
        return GLib.SOURCE_REMOVE

    def _make_page(self, group):
        page = GroupPage(group, self.groups, can_reorder=lambda: self.settings.get_string('sort') == 'manual' and not self.query)
        self.pages[group] = page
        self.tab_view.append(page).set_title(group)
        return page

    def _ask_name(self, heading, label, initial, callback, picker=None):
        entry = Gtk.Entry(text=initial, activates_default=True)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.append(entry)
        if picker:
            body.append(picker)
        dlg = Adw.AlertDialog(heading=heading, extra_child=body)
        dlg.add_response('cancel', 'Cancel')
        dlg.add_response('ok', label)
        dlg.set_response_appearance('ok', Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response('ok')
        dlg.connect('response', lambda d, r: r == 'ok' and callback(entry.get_text()))
        dlg.present(self)

    def ask_new_group(self, *_):
        picker = IconPicker(DEFAULT_ICON)
        self._ask_name('New group', 'Create', '', lambda text: self.new_group(text, picker.value()), picker)

    def new_group(self, text, icon=None):
        name = self.groups.add_group(text)
        if not name:
            self.toasts.add_toast(Adw.Toast(title='Invalid or duplicate group name'))
            return
        if icon:
            self.icons.set(name, icon)
        self.tab_view.set_selected_page(self._tab_page_of(self._make_page(name)))
        self.restart_timers()

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
        self.sources.rename_group(old, new)
        self.intervals.rename_group(old, new)
        self.icons.rename_group(old, new)
        page = self.pages.pop(old)
        page.name = new
        self.pages[new] = page
        self.tab_view.get_page(page).set_title(new)
        self._refilter()
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
        self.sources.remove_group(name)
        self.intervals.remove_group(name)
        self.icons.remove_group(name)
        self.pages.pop(name)
        self.restart_timers()
        self.tab_view.close_page_finish(tab_page, True)

    # --- repos ---
    def _add_card(self, ident, group):
        card = Card(ident, self.remove_repo, self.rename_repo, self.drag_started, self.drag_finished,
                    self.titles.get(ident), other_groups=self.other_groups, on_move=self.move_to_group,
                    can_drag=lambda: self.settings.get_string('sort') == 'manual' and not self.query)
        self.cards[ident] = card
        self.pages[group].add_slot(ident, Slot(card))
        self._apply_sort(group)

    def _others_load(self, exclude=None):
        """(github_repos, interval) of the groups that refresh alongside the one being edited: every other group,
        but only with 'Refresh groups out of focus' on (otherwise just the visible group refreshes)."""
        if not self.settings.get_boolean('refresh-all-groups'):
            return []
        default = self.settings.get_int('refresh-seconds')
        return [(sum(repo_id.host_of(r) == repo_id.GITHUB_HOST for r in self.groups.repos(g)),
                 self.intervals.effective(g, default)) for g in self.groups.names() if g != exclude]

    def ask_group_settings(self, *_):
        group, current = self._selected_group(), self.intervals.get(self._selected_group())
        github = sum(repo_id.host_of(r) == repo_id.GITHUB_HOST for r in self.groups.repos(group))
        rows = IntervalRows(self.settings.get_int('refresh-seconds'), current, github,
                            bool(self.tokens.get(repo_id.GITHUB_HOST)), self._others_load(exclude=group))
        src = next((x for x in self.sources.all() if x[0] == group), None)
        GroupSettingsDialog(group, rows, current, lambda seconds: (self.intervals.set(group, seconds),
                                                                   self.restart_timers()),
                            src and f'{src[1]}/{src[2]}',
                            src and (lambda: self.ask_browse(group, src)),
                            self.icons.get(group), lambda icon: self._set_group_icon(group, icon)).present(self)

    def _set_group_icon(self, group, icon):
        self.icons.set(group, icon)
        if (image := self.sidebar_icons.get(self._tab_page(group))):
            image.set_from_icon_name(icon)

    def ask_browse(self, group, src):
        """List every repository of the group's account (tracked ones ticked) to add more."""
        _g, host, account, kinds = src
        ImportDialog(self.settings, self.tokens, self.service, self.pool.submit, self.groups.all_repos,
                     lambda *a: self.import_account(*a, group=group), prefill=(host, account, kinds)).present(self)

    # --- import from an account ---
    def ask_import(self, *_):
        ImportDialog(self.settings, self.tokens, self.service, self.pool.submit, self.groups.all_repos,
                     self._confirm_import, self._others_load()).present(self)

    def _confirm_import(self, host, account, chosen, kinds, listed, interval):
        if self.settings.get_boolean('sync-asked'):
            self.import_account(host, account, chosen, kinds, listed, interval)
            return
        dlg = Adw.AlertDialog(heading='Keep this group in sync?',
                              body='Painel can add repositories this account creates later. You can change this in Preferences.')
        dlg.add_response('no', 'Not now')
        dlg.add_response('yes', 'Keep in sync')
        dlg.set_response_appearance('yes', Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response('yes')

        def answered(_dlg, response):
            self.settings.set_boolean('sync-imported', response == 'yes')
            self.settings.set_boolean('sync-asked', True)
            self.import_account(host, account, chosen, kinds, listed, interval)

        dlg.connect('response', answered)
        dlg.present(self)

    def import_account(self, host, account, chosen, kinds, listed, interval=None, group=None):
        """`listed` = every repo of the account (chosen or not) so sync never adds the ones skipped here."""
        wanted = importer.group_name(account)
        group = group or next((g for g in self.groups.names() if g.lower() == wanted.lower()), None)  # re-import adds to it
        if group:
            self.tab_view.set_selected_page(self._tab_page(group))
        else:
            self.new_group(wanted)
            group = wanted
        for ident in chosen:
            self.groups.add_repo(group, ident)
            self._add_card(ident, group)
        self.sources.add(group, host, account, kinds, listed)
        if interval is not None:
            self.intervals.set(group, interval)
        self.restart_timers()
        self.refresh()
        self.toasts.add_toast(Adw.Toast(title=f'Imported {len(chosen)} repositories into {group}'))

    def _sync_sources(self):
        """Add repositories an imported account created since the last listing (only with the preference on)."""
        if not self.settings.get_boolean('sync-imported'):
            return
        for group, host, account, kinds in self.sources.all():
            token = self.tokens.get(host)
            self.pool.submit(self._sync_worker, group, host, account, kinds, token)

    def _sync_worker(self, group, host, account, kinds, token):
        infos, _truncated, error = self.service.list_repos(host, account, token)
        if not error:
            GLib.idle_add(self._synced, group, host, kinds, infos)

    def _synced(self, group, host, kinds, infos):
        if group not in self.pages:  # deleted meanwhile
            return
        listed = [f'{host}/{i.path}' for i in importer.select(infos, 'forks' in kinds, 'archived' in kinds)]
        added = 0
        for ident in self.sources.take_new(group, listed):
            if self.groups.group_of(ident) is None:  # tracked elsewhere already: leave it there
                self.groups.add_repo(group, ident)
                self._add_card(ident, group)
                added += 1
        if added:
            self.refresh()
            self.toasts.add_toast(Adw.Toast(title=f'{added} new repositories in {group}'))

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
        for mirrors in self.mirrors.values():
            if name in mirrors:
                mirrors[name].set_custom_title(self.titles.get(name))
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
        self._schedule_virtual()

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
    def restart_timers(self):
        """One timer per group at its own interval (the global one unless the group has a custom one)."""
        for source in self.timers:
            GLib.source_remove(source)
        default = self.settings.get_int('refresh-seconds')
        self.timers = [GLib.timeout_add_seconds(self.intervals.effective(group, default), self._tick, group)
                       for group in self.groups.names()]

    def _tick(self, group):
        if group not in self.pages:  # renamed or deleted: restart_timers replaced this source already
            return GLib.SOURCE_REMOVE
        if self.virtual_active:  # the open virtual group keeps its member repos fresh
            visible = any(self.groups.group_of(i) == group for i in self.mirrors.get(self._selected_vid(), {}))
        else:
            visible = group == self._selected_group()
        if visible or self.settings.get_boolean('refresh-all-groups'):
            self.refresh([group])
        return GLib.SOURCE_CONTINUE

    def _on_group_focused(self):
        if not self.settings.get_boolean('refresh-all-groups'):  # otherwise it is already fresh
            self.refresh()  # new tab: refresh at once

    def refresh(self, groups=None):
        """Refresh `groups`; by default only the visible group (saves API quota), or all with the preference."""
        if not self.tab_view.get_selected_page():
            return
        tokens = {}
        if groups is None and self.virtual_active:
            names = list(self.mirrors.get(self._selected_vid(), {}))  # the repos of the open virtual group
        else:
            if groups is None:
                groups = self.groups.names() if self.settings.get_boolean('refresh-all-groups') else [self._selected_group()]
            names = [name for group in groups for name in self.groups.repos(group)]
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
            for mirrors in self.mirrors.values():
                if name in mirrors:
                    mirrors[name].update(data)
            self._apply_sort(self.groups.group_of(name))
            if not self.marks_scheduled:  # a burst of results walks the tab bar once, not once per repo
                self.marks_scheduled = GLib.idle_add(self._flush_marks)

    def _flush_marks(self):
        self.marks_scheduled = 0
        self._update_marks()
        return GLib.SOURCE_REMOVE

    def show_prefs(self):
        Prefs(self.settings, self.tokens, self.cards,
              lambda msg: self.toasts.add_toast(Adw.Toast(title=msg)),  # the rest feeds the rate-limit estimate
              groups={g: self.groups.repos(g) for g in self.groups.names()}, selected=self._selected_group(),
              custom={g: self.intervals.get(g) for g in self.groups.names() if self.intervals.get(g)}).present(self)
