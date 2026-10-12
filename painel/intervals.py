from .rate_limit import MAX_SECONDS, MIN_SECONDS


class IntervalStore:
    """Per-group refresh interval in seconds; a group without one follows the global interval.
    Persistence is injected via `save({group: seconds})`, like `TitleStore`."""

    def __init__(self, intervals, save):
        self._intervals, self._save = dict(intervals), save

    def get(self, group):
        return self._intervals.get(group)

    def effective(self, group, default):
        return self._intervals.get(group, default)

    def set(self, group, seconds):
        """`None` = back to the global interval."""
        if seconds is None:
            self._intervals.pop(group, None)
        else:
            self._intervals[group] = max(MIN_SECONDS, min(MAX_SECONDS, int(seconds)))
        self._save(dict(self._intervals))

    def rename_group(self, old, new):
        if old in self._intervals:
            self._intervals[new] = self._intervals.pop(old)
            self._save(dict(self._intervals))

    def remove_group(self, group):
        if self._intervals.pop(group, None) is not None:
            self._save(dict(self._intervals))
