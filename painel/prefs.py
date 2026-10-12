from gi.repository import Adw, Gtk

from . import repo_id
from .tokens import TokenStoreError
from .rate_limit import LIMITS, github_load, usage_text
from .notify import KINDS
from .virtual import DEFINITIONS


class Prefs(Adw.PreferencesDialog):
    def __init__(self, settings, tokens, repos, on_error, groups=None, selected=None, custom=None):
        super().__init__(title='Preferences')
        page, group = Adw.PreferencesPage(), Adw.PreferencesGroup(title='Refresh')
        page.add(group)
        self.add(page)

        interval = Adw.SpinRow.new_with_range(15, 3600, 5)
        interval.set_title('Refresh interval (seconds)')
        settings.bind('refresh-seconds', interval, 'value', 0)
        group.add(interval)
        # rate-limit estimate inputs: repos per group, the visible group, groups with their own interval
        self.interval, self.groups, self.selected, self.custom = interval, groups or {}, selected, custom or {}
        every = Adw.SwitchRow(title='Refresh groups out of focus',
                              subtitle='Also update groups you are not viewing. Uses more API requests.')
        settings.bind('refresh-all-groups', every, 'active', 0)
        every.connect('notify::active', lambda *_: self._update_warning())
        group.add(every)
        self.every = every

        look = Adw.PreferencesGroup(title='Group health marks')
        page.add(look)
        for key, title, subtitle in (('colored-tabs', 'Colored group rows', 'Tint sidebar rows by group health.'),
                                     ('colored-icons', 'Colored icons', 'Color the health icons shown on each group.')):
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            settings.bind(key, row, 'active', 0)
            look.add(row)

        notes = Adw.PreferencesGroup(title='Notifications', description='Desktop notifications when a repository\u2019s CI '
                                     'state changes, including changes that happened while the app was closed. '
                                     'Mute single groups in Group settings.')
        page.add(notes)
        master = Adw.SwitchRow(title='CI notifications')
        settings.bind('notify-ci', master, 'active', 0)
        notes.add(master)
        for kind, title in zip(KINDS, ('Failures', 'Recoveries', 'Running pipeline fails')):
            row = Adw.SwitchRow(title=title, active=kind in settings.get_strv('notify-kinds'))
            row.connect('notify::active', lambda r, _p, k=kind: self._toggle_kind(settings, k, r.get_active()))
            master.bind_property('active', row, 'sensitive', 2)  # SYNC_CREATE
            notes.add(row)

        virtual = Adw.PreferencesGroup(title='Virtual groups', description='Read-only groups in the sidebar that collect '
                                       'matching repositories from every group. Status-based ones only see repositories '
                                       'already refreshed: turn on \u201cRefresh groups out of focus\u201d to cover all groups.')
        page.add(virtual)
        for d in DEFINITIONS:
            row = Adw.SwitchRow(title=d.title, subtitle=d.subtitle, active=d.id not in settings.get_strv('virtual-disabled'))
            row.connect('notify::active', lambda r, _p, vid=d.id: self._toggle_virtual(settings, vid, r.get_active()))
            virtual.add(row)

        sync = Adw.PreferencesGroup(title='Import')
        page.add(sync)
        sync_row = Adw.SwitchRow(title='Keep imported groups in sync',
                                 subtitle='Every 30 minutes, add repositories the imported accounts created since.')
        settings.bind('sync-imported', sync_row, 'active', 0)
        sync_row.connect('notify::active', lambda *_: settings.set_boolean('sync-asked', True))  # no first-import question
        sync.add(sync_row)

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

    @staticmethod
    def _toggle_kind(settings, kind, on):
        kept = [k for k in settings.get_strv('notify-kinds') if k != kind]
        settings.set_strv('notify-kinds', [*kept, kind] if on else kept)

    @staticmethod
    def _toggle_virtual(settings, vid, on):
        off = [v for v in settings.get_strv('virtual-disabled') if v != vid]
        settings.set_strv('virtual-disabled', off if on else [*off, vid])

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
        names = list(self.groups) if self.every.get_active() else [n for n in [self.selected] if n in self.groups]
        default = self.interval.get_value()  # groups with a custom interval keep it
        load = [(sum(repo_id.host_of(r) == repo_id.GITHUB_HOST for r in self.groups[n]), self.custom.get(n, default))
                for n in names]
        has_token = bool(self.rows[repo_id.GITHUB_HOST].get_text().strip())
        per_hour = github_load(load, has_token)
        over = per_hour > LIMITS[has_token]
        self.interval.set_subtitle(usage_text(per_hour, has_token) + (' Add a token to raise it.' if over and not has_token else ''))
        (self.interval.add_css_class if over else self.interval.remove_css_class)('warning')
