from gi.repository import Adw, GLib, Gtk

from . import rate_limit, repo_id
from .importer import default_selection, wanted
from .interval_row import IntervalRows

HOSTS = ('github.com', 'gitlab.com')


class ImportDialog(Adw.Dialog):
    """Pick an account, see what it holds (public, plus private when a token is stored), tick the repositories,
    optionally set the group's refresh interval, import.
    `prefill=(host, account, kinds)` is for an already imported group: account locked, listing starts at once,
    refresh interval hidden (the group keeps its own).
    Self-contained so the entry point can move: `service.list_repos` + `submit` do the I/O, `on_import` the result."""

    def __init__(self, settings, tokens, service, submit, tracked, on_import, others=(), prefill=None):
        super().__init__(title='Import from account', content_width=460, content_height=540)
        self.settings, self.tokens, self.service, self.submit = settings, tokens, service, submit
        self.tracked, self.on_import = tracked, on_import
        self.locked = bool(prefill)
        self.found = None  # (host, account, token, infos, truncated) once listed
        self.checks, self.tracked_now = {}, set()  # ident -> CheckButton; idents already tracked when listed

        self.hosts = list(HOSTS)  # a profile URL on another GitLab host appends it
        self.host = Adw.ComboRow(title='Host', model=Gtk.StringList.new(self.hosts))
        self.account = Adw.EntryRow(title='User or organization', activates_default=True)
        self.forks = Adw.SwitchRow(title='Include forks')
        self.archived = Adw.SwitchRow(title='Include archived')
        top = Adw.PreferencesGroup()
        for row in (self.host, self.account, self.forks, self.archived):
            top.add(row)

        # shown once the account was listed
        self.picker = Adw.ExpanderRow(title='Choose repositories')
        bulk = Adw.ActionRow(title='Select')
        for label, state in (('All', True), ('None', False)):
            button = Gtk.Button(label=label, valign=Gtk.Align.CENTER, css_classes=['flat'])
            button.connect('clicked', lambda _b, on=state: self._tick_all(on))
            bulk.add_suffix(button)
        self.picker.add_row(bulk)
        self.list_rows = []
        picker_group = Adw.PreferencesGroup()
        picker_group.add(self.picker)
        self.interval = IntervalRows(settings.get_int('refresh-seconds'), others=others)
        self.interval.connect(self._summarize)
        refresh_group = Adw.PreferencesGroup(title='Refresh')
        for row in self.interval.rows:
            refresh_group.add(row)
        self.found_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, visible=False)
        self.found_box.append(picker_group)
        self.found_box.append(refresh_group)

        self.status = Gtk.Label(wrap=True, xalign=0, css_classes=['dim-label'])
        self.button = Gtk.Button(label='Find repositories', halign=Gtk.Align.CENTER,
                                 css_classes=['suggested-action', 'pill'])
        self.button.connect('clicked', lambda *_: self._import() if self.found else self._find())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12,
                      margin_start=12, margin_end=12)
        for w in (top, self.found_box):
            box.append(w)
        view = Adw.ToolbarView(content=Gtk.ScrolledWindow(child=box, propagate_natural_height=True,
                                                          hscrollbar_policy=Gtk.PolicyType.NEVER))
        view.add_top_bar(Adw.HeaderBar())
        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=12,
                         margin_start=12, margin_end=12)  # always visible, however long the picker is
        bottom.append(self.status)
        bottom.append(self.button)
        view.add_bottom_bar(bottom)
        self.set_child(view)
        self.set_default_widget(self.button)

        self.host.connect('notify::selected', lambda *_: self._reset())
        self.account.connect('changed', lambda *_: self._reset())
        self.forks.connect('notify::active', lambda *_: self._kind_toggled('fork'))
        self.archived.connect('notify::active', lambda *_: self._kind_toggled('archived'))
        if prefill:
            host, account, kinds = prefill
            if host not in self.hosts:
                self.hosts.append(host)
                self.host.set_model(Gtk.StringList.new(self.hosts))
            self.host.set_selected(self.hosts.index(host))
            self.account.set_text(account)
            self.forks.set_active('forks' in kinds)
            self.archived.set_active('archived' in kinds)
            for row in (self.host, self.account):
                row.set_sensitive(False)
            refresh_group.set_visible(False)
            self._find()

    def _reset(self):
        self.found = None
        self.found_box.set_visible(False)
        self.status.set_label('')
        self.button.set_label('Find repositories')
        self.button.set_sensitive(True)

    def _find(self):
        parsed = repo_id.parse_account(self.account.get_text(), self.hosts[self.host.get_selected()])
        if not parsed:
            self.status.set_label('Enter a user or organization name, or a profile URL.')
            return
        host, account = parsed
        if host not in self.hosts:
            self.hosts.append(host)
            self.host.set_model(Gtk.StringList.new(self.hosts))
        self.host.set_selected(self.hosts.index(host))
        self.account.set_text(account)  # both trigger _reset, so the busy state is set after them
        self.button.set_sensitive(False)
        self.status.set_label('Searching…')
        token = self.tokens.get(host)
        self.submit(self._worker, host, account, token)

    def _worker(self, host, account, token):
        infos, truncated, error = self.service.list_repos(host, account, token)
        GLib.idle_add(self._listed, host, account, token, infos, truncated, error)

    def _listed(self, host, account, token, infos, truncated, error):
        if error:
            self.status.set_label(error)
            self.button.set_sensitive(True)
            return
        self.found = (host, account, token, infos, truncated)
        self._fill_picker()
        self.found_box.set_visible(True)
        self.interval.set_github_repos(0, bool(token))
        self._summarize()
        self.interval.suggest()  # the default interval may not fit the limit for this many repos

    def _fill_picker(self):
        host, _account, _token, infos, _truncated = self.found
        for row in self.list_rows:
            self.picker.remove(row)
        self.list_rows, self.checks = [], {}
        self.tracked_now = {t.lower() for t in self.tracked()}
        picked = default_selection(infos, host, self.forks.get_active(), self.archived.get_active(), self.tracked())
        for info in infos:
            ident = f'{host}/{info.path}'
            tracked = ident.lower() in self.tracked_now
            tags = [t for t, on in (('private', info.private), ('fork', info.fork), ('archived', info.archived),
                                    ('already tracked', tracked)) if on]
            check = Gtk.CheckButton(active=tracked or ident in picked, sensitive=not tracked, valign=Gtk.Align.CENTER)
            check.connect('toggled', lambda *_: self._summarize())
            row = Adw.ActionRow(title=info.path, subtitle=' · '.join(tags), activatable_widget=check)
            row.add_prefix(check)
            self.picker.add_row(row)
            self.list_rows.append(row)
            self.checks[ident] = check

    def _kind_toggled(self, kind):
        """Switching 'forks' / 'archived' re-ticks that kind only; other manual picks stay."""
        if not self.found:
            return
        host, _account, _token, infos, _truncated = self.found
        forks, archived = self.forks.get_active(), self.archived.get_active()
        for info in infos:
            ident = f'{host}/{info.path}'
            if getattr(info, kind) and ident.lower() not in self.tracked_now:
                self.checks[ident].set_active(wanted(info, forks, archived))

    def _tick_all(self, on):
        for ident, check in self.checks.items():
            if ident.lower() not in self.tracked_now:
                check.set_active(on)

    def _chosen(self):
        return [i for i, c in self.checks.items() if c.get_active() and i.lower() not in self.tracked_now]

    def _summarize(self):
        if not self.found:
            return
        host, _account, token, infos, truncated = self.found
        chosen = self._chosen()
        open_ = [i for i in self.checks if i.lower() not in self.tracked_now]
        self.picker.set_title(f'Choose repositories ({len(chosen)} of {len(open_)})')
        lines = [f'Found {len(infos)} repositories · {len(chosen)} selected · {len(self.checks) - len(open_)} already tracked']
        if not token:
            lines.append(f'No {host} token stored: private repositories are not included.')
        elif not any(i.private for i in infos):
            lines.append('No private repositories seen (the token may not grant access to them).')
        if truncated:
            lines.append('Only the first 1000 repositories were listed.')
        self.interval.set_github_repos(len(chosen) if host == repo_id.GITHUB_HOST else 0, bool(token))
        self.status.set_label('\n'.join(lines))
        self.button.set_label(f'Import {len(chosen)} repositories' if chosen else 'Select repositories to import')
        self.button.set_sensitive(bool(chosen))

    def _import(self):
        host, account, _token, infos, _truncated = self.found
        kinds = [k for k, row in (('forks', self.forks), ('archived', self.archived)) if row.get_active()]
        chosen, listed = self._chosen(), [f'{host}/{i.path}' for i in infos]  # listed: unchosen ones must not sync in later
        self.close()
        self.on_import(host, account, chosen, kinds, listed, None if self.locked else self.interval.value())
