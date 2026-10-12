from gi.repository import Adw

from . import rate_limit


class IntervalRows:
    """"Custom refresh interval" switch + seconds spin, with the GitHub rate-limit warning and a suggestion.
    Shared by the group settings and the import dialog. `value()` is the chosen seconds, None = follow the default."""

    def __init__(self, default, current=None, github_repos=0, has_token=False):
        self.github_repos, self.has_token = github_repos, has_token
        self.switch = Adw.SwitchRow(title='Custom refresh interval', subtitle='Instead of the interval in Preferences.',
                                    active=current is not None)
        self.spin = Adw.SpinRow.new_with_range(rate_limit.MIN_SECONDS, rate_limit.MAX_SECONDS, rate_limit.STEP)
        self.spin.set_title('Refresh every (seconds)')
        self.spin.set_value(current or default)
        self.spin.set_sensitive(self.switch.get_active())
        self.rows = [self.switch, self.spin]
        self.callbacks = []
        self.switch.connect('notify::active', lambda *_: self._changed())
        self.spin.connect('notify::value', lambda *_: self._changed())
        self._warn()

    def value(self):
        return int(self.spin.get_value()) if self.switch.get_active() else None

    def connect(self, callback):
        self.callbacks.append(callback)

    def set_github_repos(self, count, has_token):
        self.github_repos, self.has_token = count, has_token
        self._warn()

    def suggest(self):
        """Switch to the shortest interval that fits the rate limit, if the current one does not."""
        if self._warning():
            self.spin.set_value(rate_limit.min_interval(self.github_repos, self.has_token))
            self.switch.set_active(True)

    def _warning(self):
        interval = self.value() or self.spin.get_value()  # off: the shown default is what applies
        return rate_limit.github_warning(interval, self.github_repos, self.has_token)

    def _warn(self):
        warning = self._warning()
        hint = f'Suggested: {rate_limit.min_interval(self.github_repos, self.has_token)} s.' if warning else ''
        self.spin.set_subtitle(f'{warning} {hint}' if warning else '')
        (self.spin.add_css_class if warning else self.spin.remove_css_class)('warning')

    def _changed(self):
        self.spin.set_sensitive(self.switch.get_active())
        self._warn()
        for callback in self.callbacks:
            callback()
