from gi.repository import Adw

from . import providers


class Prefs(Adw.PreferencesDialog):
    def __init__(self, settings, repos):
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
        self.rows = {}
        for host in dict.fromkeys(['github.com', 'gitlab.com', *map(providers.host_of, repos)]):
            row = Adw.PasswordEntryRow(title=host)
            row.set_text(providers.get_token(host) or '')
            tokens.add(row)
            self.rows[host] = row
        self.connect('closed', lambda *_: [providers.set_token(h, r.get_text().strip())
                                           for h, r in self.rows.items()])
