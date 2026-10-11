from gi.repository import Adw, Gtk

CI = {'success': ('Passing', 'success'), 'failure': ('Failing', 'error'),
      'running': ('Running', 'accent'), 'cancelled': ('Cancelled', 'warning'),
      'none': ('No CI', 'dim-label')}


class Card(Gtk.Box):
    def __init__(self, full_name, on_remove):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class('card')
        for s in ('top', 'bottom', 'start', 'end'):
            getattr(self, f'set_margin_{s}')(6)
        self.url = None
        self.title = Gtk.Label(label=full_name, xalign=0, wrap=True)
        self.title.add_css_class('title-3')
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
        for w in (self.title, self.stats, ci_row, bar):
            box.append(w)
        for s in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{s}')(12)
        self.append(box)

    def _open(self, *_):
        if self.url:
            Gtk.UriLauncher(uri=self.url).launch(self.get_root(), None, None, None)

    def update(self, s):
        self.title.set_label(s.name)
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
