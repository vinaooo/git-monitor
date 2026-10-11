from gi.repository import Adw

from . import repo_id


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

        tokens = Adw.PreferencesGroup(title='Access tokens (optional)',
                                      description='For private repos and higher rate limits')
        page.add(tokens)
        self.tokens, self.rows = tokens, {}
        for host in dict.fromkeys(['github.com', 'gitlab.com', *map(repo_id.host_of, repos)]):
            row = Adw.PasswordEntryRow(title=host)
            row.set_text(tokens.get(host) or '')
            tokens.add(row)
            self.rows[host] = row
        self.connect('closed', lambda *_: [self.tokens.set(h, r.get_text().strip())
                                           for h, r in self.rows.items()])
