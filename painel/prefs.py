from gi.repository import Adw, Gtk

from . import repo_id
from .tokens import TokenStoreError
from .rate_limit import github_warning


class Prefs(Adw.PreferencesDialog):
    def __init__(self, settings, tokens, repos, on_error, active=None):
        super().__init__(title='Preferences')
        page, group = Adw.PreferencesPage(), Adw.PreferencesGroup(title='Refresh')
        page.add(group)
        self.add(page)

        interval = Adw.SpinRow.new_with_range(15, 3600, 5)
        interval.set_title('Refresh interval (seconds)')
        settings.bind('refresh-seconds', interval, 'value', 0)
        group.add(interval)
        layout = Adw.ComboRow(title='Group layout', model=Gtk.StringList.new(['Tabs', 'Sidebar']))
        layout.set_selected(1 if settings.get_string('layout') == 'sidebar' else 0)
        layout.connect('notify::selected', lambda r, _p: settings.set_string('layout', ('tabs', 'sidebar')[r.get_selected()]))
        group.add(layout)
        self.interval, self.all_repos, self.active = interval, list(repos), list(repos if active is None else active)
        every = Adw.SwitchRow(title='Refresh groups out of focus',
                              subtitle='Also update groups you are not viewing. Uses more API requests.')
        settings.bind('refresh-all-groups', every, 'active', 0)
        every.connect('notify::active', lambda *_: self._update_warning())
        group.add(every)
        self.every = every

        look = Adw.PreferencesGroup(title='Group health marks')
        page.add(look)
        for key, title, subtitle in (('colored-tabs', 'Colored tabs', 'Tint tabs and sidebar rows by group health.'),
                                     ('colored-icons', 'Colored icons', 'Color the health icons shown on each group.')):
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            settings.bind(key, row, 'active', 0)
            look.add(row)

        token_group = Adw.PreferencesGroup(title='Access tokens (optional)',
                                      description='For private repos and higher rate limits. Use read-only tokens: '
                                                  'GitHub fine-grained (Metadata, Issues, Pull requests, '
                                                  'Actions: read) or GitLab read_api, with an expiry date.')
        page.add(token_group)
        self.tokens, self.on_error, self.rows, self.initial = tokens, on_error, {}, {}
        for host in dict.fromkeys(['github.com', 'gitlab.com', *map(repo_id.host_of, repos)]):
            row = Adw.PasswordEntryRow(title=host)
            self.initial[host] = tokens.get(host) or ''
            row.set_text(self.initial[host])
            token_group.add(row)
            self.rows[host] = row
        interval.connect('notify::value', lambda *_: self._update_warning())
        self.rows['github.com'].connect('changed', lambda *_: self._update_warning())
        self._update_warning()
        self.connect('closed', lambda *_: self._save())

    def _save(self):
        for host, row in self.rows.items():
            token = row.get_text().strip()
            if token == self.initial[host]:
                continue
            try:
                self.tokens.set(host, token)
            except TokenStoreError:
                self.on_error(f'Could not save {host} token securely (keyring unavailable)')

    def _update_warning(self):
        refreshed = self.all_repos if self.every.get_active() else self.active  # repos hit each cycle
        github = sum(repo_id.host_of(r) == repo_id.GITHUB_HOST for r in refreshed)
        has_token = bool(self.rows[repo_id.GITHUB_HOST].get_text().strip())
        warning = github_warning(self.interval.get_value(), github, has_token)
        self.interval.set_subtitle(warning or '')
        (self.interval.add_css_class if warning else self.interval.remove_css_class)('warning')
