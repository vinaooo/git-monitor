import math

from .signals import extra_calls

# Per repo per pass: (conditional REST calls, calls that always count). With a token a 304 is free (GitHub docs, not yet
# measured here); anonymous 304s are NOT: the measured quota dropped as fast as for 200s. Anonymous: repo, pulls, runs,
# running count. Token: runs, running count + this repo's share (~1 point) of the batched GraphQL query (repo + PRs).
CALLS_PER_REPO = {False: (0, 4), True: (2, 1)}
LIMITS = {False: 60, True: 5000}  # GitHub requests/hour: anonymous / with token
MIN_SECONDS, MAX_SECONDS, STEP = 15, 3600, 5  # same bounds as the refresh interval rows


def calls_per_repo(has_token, not_modified=0.0, signals=()):
    """Counted requests per repo per pass. `not_modified`: share of conditional GETs answered by 304, which GitHub
    does not count; 0 = worst case. `signals`: enabled optional card signals (signals.py)."""
    conditional, fixed = CALLS_PER_REPO[has_token]
    more_conditional, more_fixed = extra_calls(signals, has_token)
    return (conditional + more_conditional) * (1 - not_modified) + fixed + more_fixed


def github_load(groups, has_token, not_modified=0.0, signals=()):
    """GitHub requests/hour for every `(github_repos, interval)` group refreshed on its own schedule."""
    return sum(repos * calls_per_repo(has_token, not_modified, signals) * 3600 / interval for repos, interval in groups)


def usage_text(per_hour, has_token, worst=None):
    """Always-on usage line, e.g. '~1800 of 5000 requests/hour (36%)', plus the worst case once 304s lower it."""
    limit = LIMITS[has_token]
    text = f'~{per_hour:.0f} of {limit} requests/hour ({per_hour / limit:.0%})'
    if worst is not None and round(worst) > round(per_hour):
        text += f', worst case ~{worst:.0f}'
    return text


def github_warning_groups(groups, has_token, not_modified=0.0, signals=()):
    """Warning text if refreshing every `(github_repos, interval)` group exceeds GitHub's hourly limit."""
    limit, per_hour = LIMITS[has_token], github_load(groups, has_token, not_modified, signals)
    if per_hour <= limit:
        return None
    hint = '' if has_token else ' Add a token to raise it.'
    return f'~{per_hour:.0f} GitHub requests/hour, limit is {limit}.{hint}'


def github_warning(interval, github_repos, has_token, not_modified=0.0):
    """Warning text if refreshing `github_repos` every `interval` s exceeds GitHub's hourly limit."""
    return github_warning_groups([(github_repos, interval)], has_token, not_modified)


def min_interval(github_repos, has_token, not_modified=0.0, signals=()):
    """Shortest refresh interval (s, rounded up to a row step) that keeps `github_repos` under the hourly limit.
    Capped at an hour: beyond that no interval fits and the warning says so."""
    needed = github_repos * calls_per_repo(has_token, not_modified, signals) * 3600 / LIMITS[has_token]
    return min(MAX_SECONDS, max(MIN_SECONDS, math.ceil(needed / STEP) * STEP))
