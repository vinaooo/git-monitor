import re
import urllib.parse
from collections import namedtuple

from . import signals as sig
from .health import pr_bucket_github, summarize_ci, summarize_prs
from .http import HttpError
from .status import RepoInfo, RepoStatus

API = 'https://api.github.com'
MAX_PAGES = 10  # listing cap: 1000 repos
_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
_THREADS = ' reviewThreads(first: 50) { nodes { isResolved } }'  # ponytail: >50 threads on one PR are undercounted


def _pr_fields(signals):
    return """pullRequests(states: OPEN, first: 50) { totalCount nodes { number title isDraft reviewDecision mergeable%s
    commits(last: 1) { nodes { commit { statusCheckRollup { state } } } } } }""" % (_THREADS if 'reviews' in signals else '')


def _repo_fields(signals):
    """GraphQL fields of one Repository for the enabled optional signals."""
    return ''.join(f for key, f in (('security', ' vulnerabilityAlerts(states: OPEN) { totalCount }'),
                                    ('release', ' latestRelease { tagName publishedAt }'), ('push', ' pushedAt'))
                   if key in signals)


def _pr_query(signals):
    return ('query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { %s%s } }'
            % (_pr_fields(signals), _repo_fields(signals)))


def _head_fragment(signals):
    return 'fragment F on Repository { nameWithOwner url issues(states: OPEN) { totalCount } defaultBranchRef { name } %s%s }' % (
        _pr_fields(signals), _repo_fields(signals))


BATCH = 10  # repos per GraphQL query: 10 x 50 PR nodes stays well under GitHub's query time limit

# What `fetch` needs besides CI: the repo and its PRs, from one REST pair or one slot of a batched query.
Head = namedtuple('Head', 'name url issues prs pr_counts pr_details branch detail extra', defaults=({},))


class GitHubProvider:
    def __init__(self, http, signals=frozenset(), unavailable=None):
        """`signals`: enabled optional card signals. `unavailable`: shared set remembering (repo, credential) pairs
        whose code scanning answered 403/404, so they are not asked again."""
        self.http, self.signals = http, frozenset(signals)
        self.unavailable = unavailable if unavailable is not None else set()

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
        h, signals = self._headers(token), sig.usable(self.signals, token)
        decl = ', '.join(f'$o{i}: String!, $n{i}: String!' for i in range(len(paths)))
        body = ' '.join(f'r{i}: repository(owner: $o{i}, name: $n{i}) {{ ...F }}' for i in range(len(paths)))
        variables = {}
        for i, path in enumerate(paths):
            variables[f'o{i}'], variables[f'n{i}'] = path.split('/', 1)
        data, _ = self.http.post(f'{API}/graphql', {'query': f'query({decl}) {{ {body} }} {_head_fragment(signals)}',
                                                    'variables': variables}, h)
        found = data['data'] or {}
        return {path: self._head(found.get(f'r{i}'), signals) for i, path in enumerate(paths)}

    def _head(self, r, signals):
        if not r or not r.get('defaultBranchRef'):
            return None
        prs = r['pullRequests']
        counts, details = self._summary(prs['nodes'])
        extra, more = self._extra(r, signals)
        return Head(r['nameWithOwner'], r['url'], r['issues']['totalCount'], prs['totalCount'], counts,
                    {**details, **more}, r['defaultBranchRef']['name'], True, extra)

    @staticmethod
    def _extra(r, signals):
        """Optional signals out of a GraphQL Repository -> (RepoStatus fields, tooltip details). Null = no access."""
        out, details = {}, {}
        if 'security' in signals and r.get('vulnerabilityAlerts') is not None:
            out['dependabot'] = r['vulnerabilityAlerts']['totalCount']
        if 'release' in signals and r.get('latestRelease'):
            out['release'], out['released_at'] = r['latestRelease']['tagName'], r['latestRelease']['publishedAt']
        if 'push' in signals and r.get('pushedAt'):
            out['pushed_at'] = r['pushedAt']
        if 'reviews' in signals:
            counts = [(n, sum(not t['isResolved'] for t in n['reviewThreads']['nodes']))
                      for n in r['pullRequests']['nodes'] if n.get('reviewThreads')]
            out['unresolved'] = sum(c for _, c in counts)
            details['unresolved'] = [f'#{n["number"]} {n["title"]}: {c}' for n, c in counts if c]
        return out, details

    @staticmethod
    def _summary(nodes):
        return summarize_prs([(pr_bucket_github(n), f'#{n["number"]} {n["title"]}') for n in nodes])

    def fetch(self, path, token, head=None):
        """`head` from `heads()` replaces the repo and PR calls; CI always comes from conditional REST calls."""
        h = self._headers(token)
        head = head or self._head_rest(path, token, h)
        extra = dict(head.extra)
        scanning = self._code_scanning(path, token, h) if 'security' in sig.usable(self.signals, token) else None
        if scanning is not None:
            extra['code_scanning'] = scanning
        runs, _ = self.http.get(f'{API}/repos/{path}/actions/runs?branch={head.branch}&per_page=20', h)
        running, _ = self.http.get(f'{API}/repos/{path}/actions/runs?status=in_progress&per_page=1', h)
        ci_counts, ci_details, worst = summarize_ci(self._runs(runs['workflow_runs']), running['total_count'])
        return RepoStatus(name=head.name, url=head.url, prs=head.prs, issues=head.issues,
                          ci=worst, ci_counts=ci_counts, pr_counts=head.pr_counts, pr_detail=head.detail,
                          details={**{f'ci-{k}': v for k, v in ci_details.items()}, **head.pr_details}, **extra)

    def _code_scanning(self, path, token, headers):
        """Open code scanning alerts (100 = at least), None when not enabled or not permitted. Optional signal: only
        a definite 'no' (403/404/451) is remembered; any other failure just leaves the chip out this pass."""
        key = (path, token)
        if key in self.unavailable:
            return None
        try:
            alerts, _ = self.http.get(f'{API}/repos/{path}/code-scanning/alerts?state=open&per_page=100', headers)
        except HttpError as e:
            if e.code in (403, 404, 451):
                self.unavailable.add(key)
            return None
        return len(alerts) if isinstance(alerts, list) else None

    def _head_rest(self, path, token, headers):
        repo, _ = self.http.get(f'{API}/repos/{path}', headers)
        signals = sig.usable(self.signals, token)
        prs, pr_counts, pr_details, detail, extra = self._pull_requests(path, token, headers, signals)
        if not token:  # anonymous: the repo payload has the push time, the release is one more GET
            if 'push' in signals and repo.get('pushed_at'):
                extra['pushed_at'] = repo['pushed_at']
            if 'release' in signals:
                extra.update(self._release_rest(path, headers))
        return Head(repo['full_name'], repo['html_url'], repo['open_issues_count'] - prs,  # API count includes PRs
                    prs, pr_counts, pr_details, repo['default_branch'], detail, extra)

    def _release_rest(self, path, headers):
        try:
            rel, _ = self.http.get(f'{API}/repos/{path}/releases/latest', headers)
        except HttpError as e:
            if e.code == 404:  # no release yet
                return {}
            raise
        return {'release': rel['tag_name'], 'released_at': rel['published_at']}

    def _pull_requests(self, path, token, headers, signals):
        """-> (total, bucket counts, details, has review detail, optional signals). Review states need GraphQL, i.e. a token."""
        if token:
            owner, name = path.split('/', 1)
            data, _ = self.http.post(f'{API}/graphql', {'query': _pr_query(signals), 'variables': {'owner': owner, 'name': name}}, headers)
            repo = data['data']['repository']
            prs = repo['pullRequests']
            counts, details = self._summary(prs['nodes'])
            extra, more = self._extra(repo, signals)
            return prs['totalCount'], counts, {**details, **more}, True, extra
        # ponytail: anonymous REST page of 100 caps the PR total; token path is exact
        pulls, _ = self.http.get(f'{API}/repos/{path}/pulls?state=open&per_page=100', headers)
        counts, details = summarize_prs([('draft', f'#{p["number"]} {p["title"]}') for p in pulls if p['draft']])
        return len(pulls), counts, details, False, {}

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
