import urllib.parse

from .health import pr_bucket_forgejo, summarize_ci, summarize_prs
from .http import HttpError
from .status import RepoInfo, RepoStatus

# commit-status vocabulary (Forgejo/Gitea Actions and external CI both post these); skipped/warning are ignored
_CI = {'success': 'success', 'failure': 'failure', 'error': 'failure', 'pending': 'running'}

MAX_PAGES = 10  # listing cap: 500 repos
LIMIT = 50


class ForgejoProvider:
    """Forgejo and Gitea share API v1. Token = `Authorization: token <t>` (read:repository, read:issue)."""

    def __init__(self, host, http):
        self.host, self.http = host, http

    def _headers(self, token):
        return {'Authorization': f'token {token}'} if token else {}

    def list_repos(self, account, token):
        """-> ([RepoInfo], truncated): own account + token = /user/repos (private too), else org, then user."""
        h, api = self._headers(token), f'https://{self.host}/api/v1'
        own = False
        if token:
            me, _ = self.http.get(f'{api}/user', h)
            own = me['login'].lower() == account.lower()
        if own:
            base = f'{api}/user/repos?limit={LIMIT}'
        else:
            try:
                self.http.get(f'{api}/orgs/{urllib.parse.quote(account)}', h)
                base = f'{api}/orgs/{urllib.parse.quote(account)}/repos?limit={LIMIT}'
            except HttpError as e:
                if e.code != 404:
                    raise
                base = f'{api}/users/{urllib.parse.quote(account)}/repos?limit={LIMIT}'
        infos = []
        for page in range(1, MAX_PAGES + 1):
            body, _ = self.http.get(f'{base}&page={page}', h)
            infos += [RepoInfo(p['full_name'], bool(p.get('fork')), bool(p.get('archived')), bool(p.get('private')))
                      for p in body if not own or p['owner']['login'].lower() == account.lower()]
            if len(body) < LIMIT:
                return infos, False
        return infos, True

    def fetch(self, path, token):
        h = self._headers(token)
        base = f'https://{self.host}/api/v1/repos/{urllib.parse.quote(path, safe="/")}'
        repo, _ = self.http.get(base, h)
        prs, hdr = self.http.get(f'{base}/pulls?state=open&limit={LIMIT}', h)
        branch = urllib.parse.quote(repo.get('default_branch') or 'main', safe='')
        combined, _ = self.http.get(f'{base}/commits/{branch}/status?limit={LIMIT}', h)
        pr_counts, pr_details = summarize_prs([(pr_bucket_forgejo(p), f'#{p["number"]} {p["title"]}') for p in prs])
        ci_counts, ci_details, worst = summarize_ci(
            [{'key': s['context'], 'state': _CI.get(s['status'], 'ignored'), 'label': s['context'].strip(' /')}
             for s in combined.get('statuses') or []])
        return RepoStatus(name=repo['full_name'], url=repo['html_url'],
                          prs=int(hdr.get('X-Total-Count') or repo.get('open_pr_counter') or len(prs)),
                          issues=repo['open_issues_count'],  # issues only: PRs are counted apart (open_pr_counter)
                          ci=worst, ci_counts=ci_counts, pr_counts=pr_counts,
                          details={**{f'ci-{k}': v for k, v in ci_details.items()}, **pr_details})
