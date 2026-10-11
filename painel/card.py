from gi.repository import Adw, Gdk, GObject, Gtk

CI = {'success': ('Passing', 'success'), 'failure': ('Failing', 'error'),
      'running': ('Running', 'accent'), 'cancelled': ('Cancelled', 'warning'),
      'none': ('No CI', 'dim-label')}


class Card(Gtk.Box):
    def __init__(self, full_name, on_remove, on_rename, on_reorder, custom_title=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class('card')
        for s in ('top', 'bottom', 'start', 'end'):
            getattr(self, f'set_margin_{s}')(6)
        self.url, self.fetched_name, self.custom_title = None, full_name, custom_title
        self.on_rename = lambda text: on_rename(full_name, text)
        self.title = Gtk.Label(label=custom_title or full_name, xalign=0, wrap=True, hexpand=True)
        self.title.add_css_class('title-3')
        title_row = self._build_title_row()
        self.stats = Gtk.Label(label='Loading…', xalign=0)
        self.ci = Gtk.Label(xalign=0)
        self.spinner = Adw.Spinner(visible=False)
        ci_row = Gtk.Box(spacing=6)
        ci_row.append(self.spinner)
        ci_row.append(self.ci)
        open_btn = Gtk.Button(label='Open in browser', halign=Gtk.Align.START)
        open_btn.connect('clicked', self._open)
        rm = Gtk.Button(icon_name='user-trash-symbolic', tooltip_text='Remove')
        rm.add_css_class('flat')
        rm.connect('clicked', lambda *_: on_remove(full_name))
        bar = Gtk.Box(spacing=6)
        bar.append(open_btn)
        bar.append(Gtk.Box(hexpand=True))
        bar.append(rm)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for w in (title_row, self.stats, ci_row, bar):
            box.append(w)
        for s in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{s}')(12)
        self.append(box)
        self._setup_drag_and_drop(full_name, on_reorder)

    def _setup_drag_and_drop(self, ident, on_reorder):
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect('prepare', lambda *_: Gdk.ContentProvider.new_for_value(ident))
        source.connect('drag-begin', lambda src, _drag: src.set_icon(Gtk.WidgetPaintable.new(self), 0, 0))
        self.add_controller(source)
        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect('enter', lambda *_: self.set_opacity(0.6) or Gdk.DragAction.MOVE)
        target.connect('leave', lambda *_: self.set_opacity(1))
        target.connect('drop', lambda _t, src, *_: self.set_opacity(1) or on_reorder(src, ident) or True)
        self.add_controller(target)

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
            Gtk.UriLauncher(uri=self.url).launch(self.get_root(), None, None, None)

    def update(self, s):
        self.fetched_name = s.name
        self.entry.set_placeholder_text(s.name)
        self.title.set_label(self.custom_title or s.name)
        for c in ('success', 'error', 'accent', 'warning', 'dim-label'):
            self.ci.remove_css_class(c)
        if s.error:
            self.stats.set_label(s.error)
            self.ci.set_label('')
            self.spinner.set_visible(False)
            return
        self.url = s.url
        label, css = CI.get(s.ci, CI['none'])
        self.stats.set_label(f"{s.issues} open issues · {s.prs} pending PRs")
        self.ci.set_label(f'CI: {label}')
        self.ci.add_css_class(css)
        self.spinner.set_visible(s.ci == 'running')
