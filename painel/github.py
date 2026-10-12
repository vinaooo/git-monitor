import re
import urllib.parse
from collections import namedtuple

from .health import pr_bucket_github, summarize_ci, summarize_prs
from .http import HttpError
from .status import RepoInfo, RepoStatus

API = 'https://api.github.com'
MAX_PAGES = 10  # listing cap: 1000 repos
_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
_PR_FIELDS = """pullRequests(states: OPEN, first: 50) { totalCount nodes { number title isDraft reviewDecision mergeable
    commits(last: 1) { nodes { commit { statusCheckRollup { state } } } } } }"""
_PR_QUERY = 'query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { %s } }' % _PR_FIELDS
_HEAD_FRAGMENT = 'fragment F on Repository { nameWithOwner url issues(states: OPEN) { totalCount } defaultBranchRef { name } %s }' % _PR_FIELDS
BATCH = 10  # repos per GraphQL query: 10 x 50 PR nodes stays well under GitHub's query time limit

# What `fetch` needs besides CI: the repo and its PRs, from one REST pair or one slot of a batched query.
Head = namedtuple('Head', 'name url issues prs pr_counts pr_details branch detail')


class GitHubProvider:
    def __init__(self, http):
        self.http = http

    @staticmethod
    def _headers(token):
        h = {'Accept': 'application/vnd.github+json'}
        if token:
            h['Authorization'] = f'Bearer {token}'
        return h

    def list_repos(self, account, token):
        """-> ([RepoInfo], truncated). With a token, the account's private repos too (own account, or an org it can see)."""
        h, name = self._headers(token), urllib.parse.quote(account)
        if token:
            me, _ = self.http.get(f'{API}/user', h)
            if me['login'].lower() == account.lower():
                return self._pages(f'{API}/user/repos?affiliation=owner&per_page=100', h)
            try:
                return self._pages(f'{API}/orgs/{name}/repos?type=all&per_page=100', h)
            except HttpError as e:
                if e.code != 404:  # not an org: a plain user
                    raise
        return self._pages(f'{API}/users/{name}/repos?per_page=100', h)

    def _pages(self, url, headers):
        infos = []
        for _ in range(MAX_PAGES):
            body, hdr = self.http.get(url, headers)
            infos += [RepoInfo(r['full_name'], r['fork'], r['archived'], r['private']) for r in body]
            m = _NEXT.search(hdr.get('Link') or '')
            if not m:
                return infos, False
            url = m[1]
        return infos, True

    def heads(self, paths, token):
        """Repo + PR data of up to `BATCH` repos in ONE GraphQL query (needs a token) -> {path: Head | None}.
        None = not found / no access / empty repo: fetch that one over REST to get the real error."""
        h = self._headers(token)
        decl = ', '.join(f'$o{i}: String!, $n{i}: String!' for i in range(len(paths)))
        body = ' '.join(f'r{i}: repository(owner: $o{i}, name: $n{i}) {{ ...F }}' for i in range(len(paths)))
        variables = {}
        for i, path in enumerate(paths):
            variables[f'o{i}'], variables[f'n{i}'] = path.split('/', 1)
        data, _ = self.http.post(f'{API}/graphql', {'query': f'query({decl}) {{ {body} }} {_HEAD_FRAGMENT}',
                                                    'variables': variables}, h)
        found = data['data'] or {}
        return {path: self._head(found.get(f'r{i}')) for i, path in enumerate(paths)}

    def _head(self, r):
        if not r or not r.get('defaultBranchRef'):
            return None
        prs = r['pullRequests']
        counts, details = self._summary(prs['nodes'])
        return Head(r['nameWithOwner'], r['url'], r['issues']['totalCount'], prs['totalCount'], counts, details,
                    r['defaultBranchRef']['name'], True)

    @staticmethod
    def _summary(nodes):
        return summarize_prs([(pr_bucket_github(n), f'#{n["number"]} {n["title"]}') for n in nodes])

    def fetch(self, path, token, head=None):
        """`head` from `heads()` replaces the repo and PR calls; CI always comes from conditional REST calls."""
        h = self._headers(token)
        head = head or self._head_rest(path, token, h)
        runs, _ = self.http.get(f'{API}/repos/{path}/actions/runs?branch={head.branch}&per_page=20', h)
        running, _ = self.http.get(f'{API}/repos/{path}/actions/runs?status=in_progress&per_page=1', h)
        ci_counts, ci_details, worst = summarize_ci(self._runs(runs['workflow_runs']), running['total_count'])
        return RepoStatus(name=head.name, url=head.url, prs=head.prs, issues=head.issues,
                          ci=worst, ci_counts=ci_counts, pr_counts=head.pr_counts, pr_detail=head.detail,
                          details={**{f'ci-{k}': v for k, v in ci_details.items()}, **head.pr_details})

    def _head_rest(self, path, token, headers):
        repo, _ = self.http.get(f'{API}/repos/{path}', headers)
        prs, pr_counts, pr_details, detail = self._pull_requests(path, token, headers)
        return Head(repo['full_name'], repo['html_url'], repo['open_issues_count'] - prs,  # API count includes PRs
                    prs, pr_counts, pr_details, repo['default_branch'], detail)

    def _pull_requests(self, path, token, headers):
        """-> (total, bucket counts, details, has review detail). Review states need GraphQL, i.e. a token."""
        if token:
            owner, name = path.split('/', 1)
            data, _ = self.http.post(f'{API}/graphql', {'query': _PR_QUERY, 'variables': {'owner': owner, 'name': name}}, headers)
            prs = data['data']['repository']['pullRequests']
            counts, details = self._summary(prs['nodes'])
            return prs['totalCount'], counts, details, True
        # ponytail: anonymous REST page of 100 caps the PR total; token path is exact
        pulls, _ = self.http.get(f'{API}/repos/{path}/pulls?state=open&per_page=100', headers)
        counts, details = summarize_prs([('draft', f'#{p["number"]} {p["title"]}') for p in pulls if p['draft']])
        return len(pulls), counts, details, False

    @staticmethod
    def _runs(runs):
        out = []
        for r in runs:
            if r['status'] != 'completed':
                state = 'running'
            else:
                state = {'success': 'success', 'failure': 'failure', 'timed_out': 'failure',
                         'startup_failure': 'failure', 'cancelled': 'cancelled'}.get(r['conclusion'], 'ignored')
            out.append({'key': r['workflow_id'], 'state': state, 'label': r['name']})
        return out
