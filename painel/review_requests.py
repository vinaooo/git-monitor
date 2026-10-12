"""Repos with an open PR/MR that asks for MY review: one search per host per pass, not per repo."""
from . import repo_id

# ponytail: first page only (100 pending reviews); follow Link/X-Next-Page if that ever truncates
_GITHUB = 'https://api.github.com/search/issues?q=is:pr+is:open+review-requested:@me&per_page=100'


class ReviewRequests:
    def __init__(self, http):
        self.http, self._users = http, {}  # (host, token) -> GitLab user id, fetched once

    def paths(self, host, token):
        """-> lowercase repo paths; empty without a token or for hosts without a reviewer filter. Raises like providers."""
        kind = repo_id.kind(host)
        if not token or kind not in ('github', 'gitlab'):
            return set()
        if kind == 'github':  # `@me` needs no user lookup
            body, _ = self.http.get(_GITHUB, {'Accept': 'application/vnd.github+json', 'Authorization': f'Bearer {token}'})
            return {i['repository_url'].partition('/repos/')[2].lower() for i in body['items']}
        h, api = {'PRIVATE-TOKEN': token}, f'https://{host}/api/v4'
        if (host, token) not in self._users:
            self._users[host, token] = self.http.get(f'{api}/user', h)[0]['id']
        mrs, _ = self.http.get(f'{api}/merge_requests?state=opened&scope=all&reviewer_id={self._users[host, token]}&per_page=100', h)
        return {m['references']['full'].rpartition('!')[0].lower() for m in mrs}
