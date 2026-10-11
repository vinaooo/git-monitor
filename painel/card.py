from gi.repository import Adw, Gdk, Gtk, Pango

from .chips import Chip, chips_for
from .health import severity

TEXT_CHARS = 26
LOADING_CHIPS = [('CI', [Chip('…', 'dim-label', '')]), ('PRs', [Chip('…', 'dim-label', '')])]
HEALTH_CLASSES = ('health-error', 'health-warning', 'health-accent', 'health-success')


class Card(Gtk.Box):
    def __init__(self, full_name, on_remove, on_rename, on_drag_begin, on_drag_end, custom_title=None,
                 other_groups=lambda ident: [], on_move=lambda ident, group: None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class('card')
        for s in ('top', 'bottom', 'start', 'end'):
            getattr(self, f'set_margin_{s}')(6)
        self.ident, self.url, self.fetched_name, self.custom_title = full_name, None, full_name, custom_title
        self.status = None  # last RepoStatus, used by the sort menu
        self.grab_point = (0, 0)
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
        rm = Gtk.Button(icon_name='user-trash-symbolic', tooltip_text='Remove')
        rm.add_css_class('flat')
        rm.connect('clicked', lambda *_: on_remove(full_name))
        bar = Gtk.Box(spacing=6)
        bar.append(open_btn)
        self.spacer = Gtk.Box(hexpand=True)
        bar.append(self.spacer)
        bar.append(rm)
        self.box = box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for w in (title_row, self.stats, self.chips, bar):
            box.append(w)
        self.parts = (title_row, self.stats, self.chips, bar)
        for s in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{s}')(12)
        self.append(box)
        self._set_chips(LOADING_CHIPS)  # same rows as loaded: the card keeps its size when data arrives
        self._setup_drag_and_drop(full_name, on_drag_begin, on_drag_end)
        self._setup_group_menu(other_groups, on_move)

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

    def _setup_group_menu(self, other_groups, on_move):
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.connect('pressed', lambda _g, _n, x, y: self._show_group_menu(other_groups(self.ident), on_move, x, y))
        self.add_controller(click)

    def _show_group_menu(self, groups, on_move, x, y):
        if not groups:
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Gtk.Label(label='Move to group', xalign=0, margin_start=6, margin_bottom=4, css_classes=['dim-label']))
        popover = Gtk.Popover(child=box, has_arrow=False, halign=Gtk.Align.START)
        popover.set_parent(self)
        popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        popover.connect('closed', lambda p: p.unparent())
        for group in groups:
            btn = Gtk.Button(label=group, halign=Gtk.Align.FILL, css_classes=['flat'])
            btn.get_child().set_xalign(0)
            btn.connect('clicked', lambda _b, g=group: (popover.popdown(), on_move(self.ident, g)))
            box.append(btn)
        popover.popup()

    def _on_prepare(self, ident, x, y):
        self.grab_point = (int(x), int(y))  # where inside the card the press happened
        return Gdk.ContentProvider.new_for_value(ident)

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
        self.status = s
        self.fetched_name = s.name
        self.entry.set_placeholder_text(s.name)
        self.title.set_label(self.custom_title or s.name)
        for css in HEALTH_CLASSES:
            self.remove_css_class(css)
        self._set_chips(chips_for(s))
        if s.error:
            self.stats.set_label(s.error)
            return
        self.url = s.url
        self.stats.set_label(f'{s.issues} open issues')
        if severity(s) != 'none':
            self.add_css_class(f'health-{severity(s)}')

    def _chip_label(self, chip):
        label = Gtk.Label(label=chip.text, css_classes=['chip', chip.css], tooltip_text=chip.tooltip or None)
        if chip.url:  # PR/MR chips open the matching list in the browser
            label.add_css_class('chip-link')
            label.set_cursor(Gdk.Cursor.new_from_name('pointer'))
            click = Gtk.GestureClick()
            click.connect('released', lambda *_: self._launch(chip.url))
            label.add_controller(click)
            label.set_tooltip_text((chip.tooltip + '\n\n' if chip.tooltip else '') + 'Click to open in browser')
        return label

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
