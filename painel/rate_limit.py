CALLS_PER_REPO = {False: 4, True: 3}  # REST calls per repo: repo, [pulls only anonymous], runs, running count
LIMITS = {False: 60, True: 5000}  # GitHub requests/hour: anonymous / with token


def github_warning(interval, github_repos, has_token):
    """Warning text if refreshing `github_repos` every `interval` s exceeds GitHub's hourly limit."""
    limit = LIMITS[has_token]
    per_hour = github_repos * CALLS_PER_REPO[has_token] * 3600 / interval
    if per_hour <= limit:
        return None
    hint = '' if has_token else ' Add a token to raise it.'
    return f'~{per_hour:.0f} GitHub requests/hour, limit is {limit}.{hint}'
