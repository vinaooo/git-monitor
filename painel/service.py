from .forgejo import ForgejoProvider
from .github import BATCH, GitHubProvider
from .gitlab import GitLabProvider
from .http import HttpError, NetworkError
from .review_requests import ReviewRequests
from .repo_id import GITHUB_HOST, is_forgejo_host, is_gitlab_host
from .status import RepoStatus

_HTTP_MESSAGES = {404: 'Not found (private? add a token)', 401: 'Invalid token',
                  403: 'Forbidden or rate limited (add a token)', 429: 'Rate limited (add a token)'}

API_HOST = {GITHUB_HOST: 'api.github.com'}  # identity host -> host the requests go to
_FAILURES = (HttpError, NetworkError, KeyError, IndexError, ValueError, TypeError)


def _message(e):
    if isinstance(e, HttpError):
        return _HTTP_MESSAGES.get(e.code, f'HTTP {e.code}')
    if isinstance(e, NetworkError):
        return f'Network error: {e}'
    return 'Unexpected API response'


class StatusService:
    """Resolves the provider for an identity and turns failures into RepoStatus(error=...)."""

    def __init__(self, http, signals=frozenset):
        """`signals`: callable -> enabled optional card signals, read on every request so toggles apply at once."""
        self.http, self.signals, self.unavailable = http, signals, set()
        self._reviews = ReviewRequests(http)

    def _github(self):
        return GitHubProvider(self.http, self.signals(), self.unavailable)

    def _provider(self, host):
        if host == GITHUB_HOST:
            return self._github()
        if is_gitlab_host(host):
            return GitLabProvider(host, self.http)
        if is_forgejo_host(host):
            return ForgejoProvider(host, self.http)
        return None

    @staticmethod
    def batch_size(host, token):
        """Repos per batched query for `host`; 0 = fetch one by one (batching needs GitHub GraphQL, i.e. a token)."""
        return BATCH if host == GITHUB_HOST and token else 0

    def heads(self, idents, token):
        """-> {ident: Head | None} for same-host `idents` in one request; {} if the batch itself failed, so the
        caller fetches each repo alone. None = that repo needs the REST path (and its real error message)."""
        paths = [i.partition('/')[2] for i in idents]
        try:
            return dict(zip(idents, self._github().heads(paths, token).values()))
        except _FAILURES:
            return {}

    def fetch(self, ident, token, head=None):
        host, _, path = ident.partition('/')
        provider = self._provider(host)
        if provider is None:
            return RepoStatus(name=path, error=f'Unsupported host {host}')
        try:
            return provider.fetch(path, token, head) if head else provider.fetch(path, token)
        except _FAILURES as e:
            return RepoStatus(name=path, error=_message(e))

    def review_requests(self, host, token):
        """Lowercase repo paths on `host` with a PR/MR asking for my review; failures are not errors: empty set."""
        try:
            return self._reviews.paths(host, token)
        except _FAILURES:
            return set()

    def wait(self, host):
        """Seconds the server asked us to stay away from `host` (Retry-After, exhausted quota); 0 = go ahead."""
        state = getattr(self.http, 'state', None)
        return state.wait(API_HOST.get(host, host)) if state else 0

    def not_modified_ratio(self):
        """Share of recent GETs answered by 304 (free on GitHub's limit); 0 until measured."""
        ratio = getattr(self.http, 'hit_ratio', None)
        return ratio() if ratio else 0.0

    def list_repos(self, host, account, token):
        """-> ([RepoInfo], truncated, error): an account's repositories, failures as a message like `fetch`."""
        provider = self._provider(host)
        if provider is None:
            return [], False, f'Unsupported host {host}'
        try:
            infos, truncated = provider.list_repos(account, token)
            return infos, truncated, None
        except _FAILURES as e:
            return [], False, _message(e)
