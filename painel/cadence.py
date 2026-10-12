import math

from .rate_limit import MAX_SECONDS, MIN_SECONDS

IDLE_AFTER = 3          # unchanged passes before slowing down; twice that = the second step
BACKOFF_CAP = 900       # s: longest wait after failed passes


def next_delay(base, idle, errors, wait=0):
    """Seconds until the group's next pass. `base` is the group's own interval; `idle` = consecutive passes
    with nothing new and no CI running; `errors` = consecutive passes where every repo failed; `wait` = what the
    server asked for (Retry-After, rate-limit reset), a floor."""
    if errors:
        delay = max(base, min(base * 2 ** errors, BACKOFF_CAP))
    elif idle >= IDLE_AFTER:
        delay = min(base * (4 if idle >= 2 * IDLE_AFTER else 2), MAX_SECONDS)
    else:
        delay = base
    return max(delay, math.ceil(wait))


class Pace:
    """One group's refresh rhythm. Call `begin(n)` when a pass submits n repos, `result(...)` as each answers."""

    def __init__(self):
        self.idle = self.errors = 0
        self.left = self.changed = self.running = self.failed = 0
        self.total = 0

    def begin(self, n):
        if n:
            if not self.left:
                self.total = self.changed = self.running = self.failed = 0
            self.left += n
            self.total += n

    def result(self, changed, running, error):
        """-> True when this result completed the pass. Ignored without a pass in progress (fast lane)."""
        if not self.left:
            return False
        self.left -= 1
        self.changed += changed
        self.running += running
        self.failed += error
        if self.left:
            return False
        self.idle = 0 if self.changed or self.running else self.idle + 1
        self.errors = self.errors + 1 if self.failed == self.total else 0
        return True

    def delay(self, base, wait=0):
        return next_delay(base, self.idle, self.errors, wait)
