import math

CALLS_PER_REPO = {False: 4, True: 3}  # REST calls per repo: repo, [pulls only anonymous], runs, running count
LIMITS = {False: 60, True: 5000}  # GitHub requests/hour: anonymous / with token
MIN_SECONDS, MAX_SECONDS, STEP = 15, 3600, 5  # same bounds as the refresh interval rows


def github_load(groups, has_token):
    """GitHub requests/hour for every `(github_repos, interval)` group refreshed on its own schedule."""
    return sum(repos * CALLS_PER_REPO[has_token] * 3600 / interval for repos, interval in groups)


def usage_text(per_hour, has_token):
    """Always-on usage line, e.g. '~1800 of 5000 requests/hour (36%)'."""
    limit = LIMITS[has_token]
    return f'~{per_hour:.0f} of {limit} requests/hour ({per_hour / limit:.0%})'


def github_warning_groups(groups, has_token):
    """Warning text if refreshing every `(github_repos, interval)` group exceeds GitHub's hourly limit."""
    limit, per_hour = LIMITS[has_token], github_load(groups, has_token)
    if per_hour <= limit:
        return None
    hint = '' if has_token else ' Add a token to raise it.'
    return f'~{per_hour:.0f} GitHub requests/hour, limit is {limit}.{hint}'


def github_warning(interval, github_repos, has_token):
    """Warning text if refreshing `github_repos` every `interval` s exceeds GitHub's hourly limit."""
    return github_warning_groups([(github_repos, interval)], has_token)


def min_interval(github_repos, has_token):
    """Shortest refresh interval (s, rounded up to a row step) that keeps `github_repos` under the hourly limit.
    Capped at an hour: beyond that no interval fits and the warning says so."""
    needed = github_repos * CALLS_PER_REPO[has_token] * 3600 / LIMITS[has_token]
    return min(MAX_SECONDS, max(MIN_SECONDS, math.ceil(needed / STEP) * STEP))
