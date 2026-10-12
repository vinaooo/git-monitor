from gi.repository import Adw, GLib, Gtk

from . import rate_limit, repo_id
from .importer import plan, select

HOSTS = ('github.com', 'gitlab.com')


class ImportDialog(Adw.Dialog):
    """Pick an account, see what it holds (public, plus private when a token is stored), choose the kinds, import.
    Self-contained so the entry point can move: `service.list_repos` + `submit` do the I/O, `on_import` the result."""

    def __init__(self, settings, tokens, service, submit, tracked, on_import):
        super().__init__(title='Import from account', content_width=440)
        self.settings, self.tokens, self.service, self.submit = settings, tokens, service, submit
        self.tracked, self.on_import = tracked, on_import
        self.found = None  # (host, account, token, infos, truncated) once listed

        self.hosts = list(HOSTS)  # a profile URL on another GitLab host appends it
        self.host = Adw.ComboRow(title='Host', model=Gtk.StringList.new(self.hosts))
        self.account = Adw.EntryRow(title='User or organization', activates_default=True)
        self.forks = Adw.SwitchRow(title='Include forks')
        self.archived = Adw.SwitchRow(title='Include archived')
        group = Adw.PreferencesGroup()
        for row in (self.host, self.account, self.forks, self.archived):
            group.add(row)
        self.status = Gtk.Label(wrap=True, xalign=0, css_classes=['dim-label'], margin_top=6)
        self.button = Gtk.Button(label='Find repositories', halign=Gtk.Align.CENTER, margin_top=12,
                                 css_classes=['suggested-action', 'pill'])
        self.button.connect('clicked', lambda *_: self._import() if self.found else self._find())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=12, margin_bottom=24, margin_start=12, margin_end=12)
        for w in (group, self.status, self.button):
            box.append(w)
        view = Adw.ToolbarView(content=box)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)
        self.set_default_widget(self.button)

        self.host.connect('notify::selected', lambda *_: self._reset())
        self.account.connect('changed', lambda *_: self._reset())
        for row in (self.forks, self.archived):
            row.connect('notify::active', lambda *_: self._summarize())

    def _reset(self):
        self.found = None
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
        else:
            self.found = (host, account, token, infos, truncated)
            self._summarize()

    def _plan(self):
        host, _account, _token, infos, _truncated = self.found
        return plan(infos, host, self.forks.get_active(), self.archived.get_active(), self.tracked())

    def _summarize(self):
        if not self.found:
            return
        host, account, token, infos, truncated = self.found
        new, tracked = self._plan()
        private = sum(i.private for i in infos)
        lines = [f'Found {len(infos)} repositories · {len(new)} to import · {tracked} already tracked']
        if not token:
            lines.append(f'No {host} token stored: private repositories are not included.')
        elif not private:
            lines.append('No private repositories seen (the token may not grant access to them).')
        if truncated:
            lines.append('Only the first 1000 repositories were listed.')
        if host == repo_id.GITHUB_HOST:
            warning = rate_limit.github_warning(self.settings.get_int('refresh-seconds'), len(new), bool(token))
            if warning:
                lines.append(warning)
        self.status.set_label('\n'.join(lines))
        self.button.set_label(f'Import {len(new)} repositories' if new else 'Nothing new to import')
        self.button.set_sensitive(bool(new))

    def _import(self):
        host, account, _token, infos, _truncated = self.found
        new, _ = self._plan()
        kinds = [k for k, row in (('forks', self.forks), ('archived', self.archived)) if row.get_active()]
        selected = [f'{host}/{i.path}' for i in select(infos, self.forks.get_active(), self.archived.get_active())]
        self.close()
        self.on_import(host, account, new, kinds, selected)
