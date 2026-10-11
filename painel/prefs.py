from gi.repository import Adw

from . import repo_id
from .rate_limit import github_warning


class Prefs(Adw.PreferencesDialog):
    def __init__(self, settings, tokens, repos):
        super().__init__(title='Preferences')
        page, group = Adw.PreferencesPage(), Adw.PreferencesGroup(title='Refresh')
        page.add(group)
        self.add(page)

        interval = Adw.SpinRow.new_with_range(15, 3600, 5)
        interval.set_title('Refresh interval (seconds)')
        settings.bind('refresh-seconds', interval, 'value', 0)
        group.add(interval)
        self.interval, self.repos = interval, repos

        token_group = Adw.PreferencesGroup(title='Access tokens (optional)',
                                      description='For private repos and higher rate limits')
        page.add(token_group)
        self.tokens, self.rows = tokens, {}
        for host in dict.fromkeys(['github.com', 'gitlab.com', *map(repo_id.host_of, repos)]):
            row = Adw.PasswordEntryRow(title=host)
            row.set_text(tokens.get(host) or '')
            token_group.add(row)
            self.rows[host] = row
        interval.connect('notify::value', lambda *_: self._update_warning())
        self.rows['github.com'].connect('changed', lambda *_: self._update_warning())
        self._update_warning()
        self.connect('closed', lambda *_: [self.tokens.set(h, r.get_text().strip())
                                           for h, r in self.rows.items()])

    def _update_warning(self):
        github = sum(repo_id.host_of(r) == repo_id.GITHUB_HOST for r in self.repos)
        has_token = bool(self.rows[repo_id.GITHUB_HOST].get_text().strip())
        warning = github_warning(self.interval.get_value(), github, has_token)
        self.interval.set_subtitle(warning or '')
        (self.interval.add_css_class if warning else self.interval.remove_css_class)('warning')
