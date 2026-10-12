from gi.repository import Adw

from . import rate_limit


class IntervalRows:
    """"Custom refresh interval" switch + seconds spin, with the GitHub rate-limit warning and a suggestion.
    Shared by the group settings and the import dialog. `value()` is the chosen seconds, None = follow the default."""

    def __init__(self, default, current=None, github_repos=0, has_token=False, others=(), ratio=0.0):
        """`others`: (github_repos, interval) of the other groups that refresh alongside this one."""
        self.default, self.github_repos, self.has_token, self.others = default, github_repos, has_token, list(others)
        self.ratio = ratio  # share of requests answered by 304 (free on GitHub), measured by the HTTP client
        self.switch = Adw.SwitchRow(title='Custom refresh interval', subtitle='Instead of the interval in Preferences.',
                                    active=current is not None)
        self.spin = Adw.SpinRow.new_with_range(rate_limit.MIN_SECONDS, rate_limit.MAX_SECONDS, rate_limit.STEP)
        self.spin.set_title('Refresh every (seconds)')
        self.spin.set_value(current or default)
        self.spin.set_sensitive(self.switch.get_active())
        self.usage = Adw.ActionRow(title='GitHub API usage')  # always shown: the budget is shared by every group
        self.rows = [self.switch, self.spin, self.usage]
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
        if self._warn():
            self.spin.set_value(rate_limit.min_interval(self.github_repos, self.has_token, self.ratio))
            self.switch.set_active(True)

    def _interval(self):
        return self.value() or self.default  # switch off: the Preferences interval applies

    def _warn(self):
        load = rate_limit.github_load
        mine = load([(self.github_repos, self._interval())], self.has_token, self.ratio)
        total = mine + load(self.others, self.has_token, self.ratio)
        limit = rate_limit.LIMITS[self.has_token]
        over = total > limit
        worst_mine = load([(self.github_repos, self._interval())], self.has_token)
        text = f'This group {rate_limit.usage_text(mine, self.has_token, worst_mine)}'
        if self.others:
            text += f'\nAll groups {rate_limit.usage_text(total, self.has_token, worst_mine + load(self.others, self.has_token))}'
        if over:
            text += f'\nSuggested: {rate_limit.min_interval(self.github_repos, self.has_token, self.ratio)} s.'
        self.usage.set_subtitle(text)
        (self.usage.add_css_class if total >= 0.8 * limit else self.usage.remove_css_class)('warning')  # amber from 80%
        return over

    def _changed(self):
        self.spin.set_sensitive(self.switch.get_active())
        self._warn()
        for callback in self.callbacks:
            callback()
