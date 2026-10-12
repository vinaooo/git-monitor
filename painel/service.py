from .github import GitHubProvider
from .gitlab import GitLabProvider
from .http import HttpError, NetworkError
from .repo_id import GITHUB_HOST, host_of, is_gitlab_host
from .status import RepoStatus

_HTTP_MESSAGES = {404: 'Not found (private? add a token)', 401: 'Invalid token',
                  403: 'Forbidden or rate limited (add a token)', 429: 'Rate limited (add a token)'}

_FAILURES = (HttpError, NetworkError, KeyError, IndexError, ValueError, TypeError)


def _message(e):
    if isinstance(e, HttpError):
        return _HTTP_MESSAGES.get(e.code, f'HTTP {e.code}')
    if isinstance(e, NetworkError):
        return f'Network error: {e}'
    return 'Unexpected API response'


class StatusService:
    """Resolves the provider for an identity and turns failures into RepoStatus(error=...)."""

    def __init__(self, http):
        self.http = http

    def _provider(self, host):
        if host == GITHUB_HOST:
            return GitHubProvider(self.http)
        if is_gitlab_host(host):
            return GitLabProvider(host, self.http)
        return None

    def fetch(self, ident, token):
        host, _, path = ident.partition('/')
        provider = self._provider(host)
        if provider is None:
            return RepoStatus(name=path, error=f'Unsupported host {host}')
        try:
            return provider.fetch(path, token)
        except _FAILURES as e:
            return RepoStatus(name=path, error=_message(e))

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
