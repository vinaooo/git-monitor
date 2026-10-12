from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from . import local
from .chips import Chip, chips_for
from .health import severity

TEXT_CHARS = 26
LINK = 'painel:link-clone'  # Chip.url marker: the chip is a button that opens the folder picker
LOADING_CHIPS = [('CI', [Chip('…', 'dim-label', '')]), ('PRs', [Chip('…', 'dim-label', '')])]
HEALTH_CLASSES = ('health-error', 'health-warning', 'health-accent', 'health-success')


class Card(Gtk.Box):
    def __init__(self, full_name, on_remove, on_rename, on_drag_begin, on_drag_end, custom_title=None,
                 other_groups=lambda ident: [], on_move=lambda ident, group: None, can_drag=lambda: True,
                 on_link=None, on_unlink=None, linked=lambda ident: False, offer=lambda: False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class('card')
        for s in ('top', 'bottom', 'start', 'end'):
            getattr(self, f'set_margin_{s}')(6)
        self.ident, self.url, self.fetched_name, self.custom_title = full_name, None, full_name, custom_title
        self.status = None  # last RepoStatus, used by the sort menu
        self.local = None   # LocalState of the linked clone (local.py), None = unlinked or signal off
        self.on_link, self.on_unlink, self.linked, self.offer = on_link, on_unlink, linked, offer
        self.grab_point, self.can_drag = (0, 0), can_drag
        self.on_rename = lambda text: on_rename(full_name, text)
        # width is capped so a long name (or the host-prefixed identity shown before the first fetch) cannot widen
        # every card: FlowBox sizes the grid from the widest natural width
        self.title = Gtk.Label(label=custom_title or full_name.partition('/')[2], xalign=0, wrap=True,
                               wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=TEXT_CHARS, hexpand=True)
        self.title.add_css_class('title-3')
        title_row = self._build_title_row()
        self.stats = Gtk.Label(label='Loading…', xalign=0, wrap=True, max_width_chars=TEXT_CHARS)  # errors can be long
        self.chips = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)  # one wrapping row per group
        open_btn = Gtk.Button(label='Open in browser', halign=Gtk.Align.START)
        open_btn.connect('clicked', self._open)
        more = Gtk.MenuButton(icon_name='view-more-symbolic', tooltip_text='Card actions', css_classes=['flat'])
        more.set_create_popup_func(lambda btn: btn.set_menu_model(self._build_menu()))  # groups change: build per opening
        bar = Gtk.Box(spacing=6)
        bar.append(open_btn)
        self.spacer = Gtk.Box(hexpand=True)
        bar.append(self.spacer)
        bar.append(more)
        self.box = box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for w in (title_row, self.stats, self.chips, bar):
            box.append(w)
        self.parts = (title_row, self.stats, self.chips, bar)
        for s in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{s}')(12)
        self.append(box)
        self._set_chips(LOADING_CHIPS)  # same rows as loaded: the card keeps its size when data arrives
        self._setup_drag_and_drop(full_name, on_drag_begin, on_drag_end)
        self._setup_group_menu(other_groups, on_move, on_remove)

    def set_compact(self, compact):
        """List view: everything on one row instead of stacked."""
        self.box.set_orientation(Gtk.Orientation.HORIZONTAL if compact else Gtk.Orientation.VERTICAL)
        self.box.set_spacing(24 if compact else 8)
        self.spacer.set_hexpand(not compact)
        for part in self.parts:
            part.set_valign(Gtk.Align.CENTER if compact else Gtk.Align.FILL)

    def _setup_drag_and_drop(self, ident, on_drag_begin, on_drag_end):
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect('prepare', lambda _src, x, y: self._on_prepare(ident, x, y))
        source.connect('drag-begin', lambda src, _drag: self._on_drag_begin(src, ident, on_drag_begin))
        source.connect('drag-end', lambda *_: self._on_drag_end(ident, on_drag_end))
        self.add_controller(source)

    def _setup_group_menu(self, other_groups, on_move, on_remove):
        """One context menu (right-click, long-press, Menu key / Shift+F10): rename, open, move, remove."""
        self.other_groups = other_groups
        actions = Gio.SimpleActionGroup()
        for name, cb, param in (('rename', lambda *_: self._start_edit(), None), ('open', self._open, None),
                                ('remove', lambda *_: on_remove(self.ident), None),
                                ('link', lambda *_: self.on_link(self.ident), None),
                                ('unlink', lambda *_: self.on_unlink(self.ident), None),
                                ('move', lambda _a, g: on_move(self.ident, g.get_string()), GLib.VariantType('s'))):
            act = Gio.SimpleAction.new(name, param)
            act.connect('activate', cb)
            actions.add_action(act)
        self.insert_action_group('card', actions)
        for gesture in (Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY), Gtk.GestureLongPress()):
            gesture.connect('pressed', lambda _g, *a: self._show_menu(*a[-2:]))
            self.add_controller(gesture)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._on_menu_key)
        self.add_controller(keys)

    def _on_menu_key(self, _ctl, keyval, _code, state):
        if keyval == Gdk.KEY_Menu or (keyval == Gdk.KEY_F10 and state & Gdk.ModifierType.SHIFT_MASK):
            self._show_menu(self.get_width() / 2, self.get_height() / 2)
            return True
        return False

    def _build_menu(self):
        menu = Gio.Menu()
        menu.append('Rename…', 'card.rename')
        if self.url:
            menu.append('Open in browser', 'card.open')
        groups = self.other_groups(self.ident)
        if groups:
            moves = Gio.Menu()
            for group in groups:
                moves.append(group, Gio.Action.print_detailed_name('card.move', GLib.Variant('s', group)))
            menu.append_submenu('Move to group', moves)
        if self.on_link:
            if self.linked(self.ident):
                menu.append('Relink local clone…', 'card.link')
                menu.append('Unlink local clone', 'card.unlink')
            else:
                menu.append('Link local clone…', 'card.link')
        menu.append('Remove', 'card.remove')
        return menu

    def _show_menu(self, x, y):
        popover = Gtk.PopoverMenu.new_from_model(self._build_menu())
        popover.set_has_arrow(False)
        popover.set_halign(Gtk.Align.START)
        popover.set_parent(self)
        popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        popover.connect('closed', lambda p: GLib.idle_add(p.unparent))  # after the chosen action ran
        popover.popup()

    def _on_prepare(self, ident, x, y):
        if not self.can_drag():  # a sort mode owns the order: no drag at all
            return None
        self.grab_point = (int(x), int(y))  # where inside the card the press happened
        return Gdk.ContentProvider.new_for_value(GLib.Variant('s', ident))  # not text: a terminal would accept (and ptyxis crash on) a string drop

    def _on_drag_begin(self, source, ident, callback):
        # static snapshot as drag icon, then blank the card: the empty slot is the live drop preview
        source.set_icon(Gtk.WidgetPaintable.new(self).get_current_image(), *self.grab_point)  # hotspot = grab point: no jump
        self.set_opacity(0)
        callback(ident)

    def _on_drag_end(self, ident, callback):
        self.set_opacity(1)
        callback(ident)

    def _build_title_row(self):
        self.pencil = Gtk.Button(icon_name='document-edit-symbolic', tooltip_text='Rename card',
                                 valign=Gtk.Align.CENTER, opacity=0)
        self.pencil.add_css_class('flat')
        self.pencil.connect('clicked', lambda *_: self._start_edit())
        view = Gtk.Box(spacing=6)
        view.append(self.title)
        view.append(self.pencil)

        self.entry = Gtk.Entry(hexpand=True, placeholder_text=self.fetched_name,
                               tooltip_text='Leave empty to restore the original name')
        self.entry.connect('activate', lambda *_: self._confirm_edit())
        esc = Gtk.EventControllerKey()
        esc.connect('key-pressed', self._on_entry_key)
        self.entry.add_controller(esc)
        ok = Gtk.Button(icon_name='object-select-symbolic', tooltip_text='Confirm')
        ok.add_css_class('flat')
        ok.connect('clicked', lambda *_: self._confirm_edit())
        edit = Gtk.Box(spacing=6)
        edit.append(self.entry)
        edit.append(ok)

        self.title_stack = Gtk.Stack()
        self.title_stack.add_named(view, 'view')
        self.title_stack.add_named(edit, 'edit')

        self.hovered = False
        motion = Gtk.EventControllerMotion()  # pencil only while the pointer is over the card
        motion.connect('enter', lambda *_: self._set_hover(True))
        motion.connect('leave', lambda *_: self._set_hover(False))
        self.add_controller(motion)
        focus = Gtk.EventControllerFocus()  # keyboard users can reach it too
        focus.connect('enter', lambda *_: self._sync_pencil())
        focus.connect('leave', lambda *_: self._sync_pencil())
        self.pencil.add_controller(focus)
        return self.title_stack

    def _set_hover(self, hovered):
        self.hovered = hovered
        self._sync_pencil()

    def _leave_edit(self):
        self.title_stack.set_visible_child_name('view')
        root = self.get_root()
        if root:
            root.set_focus(None)  # else GTK parks focus on the pencil and keeps it shown
        self._sync_pencil()

    def _sync_pencil(self):
        # has_visible_focus: keyboard focus only, a mouse click must not pin the pencil
        self.pencil.set_opacity(1 if self.hovered or self.pencil.has_visible_focus() else 0)

    def _start_edit(self):
        self.entry.set_text(self.custom_title or self.fetched_name)
        self.title_stack.set_visible_child_name('edit')
        self.entry.grab_focus()

    def _confirm_edit(self):
        self.on_rename(self.entry.get_text())

    def _on_entry_key(self, _ctl, keyval, *_):
        if keyval == Gdk.KEY_Escape:
            self._leave_edit()
            return True
        return False

    def set_custom_title(self, title):
        self.custom_title = title
        self.title.set_label(title or self.fetched_name)
        self._leave_edit()

    def _open(self, *_):
        if self.url:
            self._launch(self.url)

    def update(self, s):
        # a failed refresh keeps the last good data on screen (dimmed) instead of wiping it
        stale = bool(s.error and self.status and not self.status.error)
        for css in HEALTH_CLASSES:
            self.remove_css_class(css)
        self.stats.remove_css_class('error')
        self.chips.set_opacity(0.5 if stale else 1)
        if stale:
            self.stats.set_label(f'Couldn’t refresh · {s.error}')
            self.stats.add_css_class('error')
            self.add_css_class('health-error')
            return
        self.status = s
        self.fetched_name = s.name
        self.entry.set_placeholder_text(s.name)
        self.title.set_label(self.custom_title or s.name)
        self._render()
        if s.error:
            self.stats.set_label(s.error)
            self.stats.add_css_class('error')
            self.add_css_class('health-error')
            return
        self.url = s.url
        self.stats.set_label(f'{s.issues} open issue{"" if s.issues == 1 else "s"}')
        if severity(s) != 'none':
            self.add_css_class(f'health-{severity(s)}')

    def set_local(self, state):
        self.local = state
        self._render()

    def _render(self):
        base = chips_for(self.status) if self.status else LOADING_CHIPS
        git = local.chips(self.local)
        if not git and self.on_link and self.offer() and not self.linked(self.ident):  # keeps the row, and the card height, uniform
            git = [Chip('+ Link local clone', 'dim-label', 'Show branch, ahead/behind and changes of your clone', LINK)]
        self._set_chips(base + ([('Git', git)] if git else []))

    def _chip_label(self, chip):
        if chip.url == LINK:
            button = Gtk.Button(label=chip.text, css_classes=['flat', 'chip', 'chip-link', chip.css], tooltip_text=chip.tooltip)
            button.connect('clicked', lambda *_: self.on_link(self.ident))
            return button
        if chip.url:  # PR/MR chips open the matching list in the browser; a real button so keyboard/Orca reach it
            button = Gtk.Button(label=chip.text, css_classes=['flat', 'chip', 'chip-link', chip.css],
                                tooltip_text=(chip.tooltip + '\n\n' if chip.tooltip else '') + 'Open in browser')
            button.connect('clicked', lambda *_: self._launch(chip.url))
            return button
        return Gtk.Label(label=chip.text, css_classes=['chip', chip.css], tooltip_text=chip.tooltip or None)

    def _launch(self, url):
        Gtk.UriLauncher(uri=url).launch(self.get_root(), None, None, None)

    def _set_chips(self, groups):
        while child := self.chips.get_first_child():
            self.chips.remove(child)
        for name, chips in groups:
            # FlowBox, not Adw.WrapBox: WrapBox's natural_line_length trips GTK's min<=natural check;
            # capping children per line keeps the card narrow so the grid still gets columns
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False, min_children_per_line=1,
                               max_children_per_line=2, column_spacing=6, row_spacing=4, halign=Gtk.Align.START)
            for chip in chips:
                flow.append(self._chip_label(chip))
            row = Gtk.Box(spacing=8, valign=Gtk.Align.START)
            row.append(Gtk.Label(label=name, css_classes=['dim-label', 'caption'], width_chars=3, xalign=0, yalign=0.5))
            row.append(flow)
            self.chips.append(row)
