from .health import pr_bucket_github, summarize_ci, summarize_prs
from .status import RepoStatus

API = 'https://api.github.com'
_PR_QUERY = """query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) {
  pullRequests(states: OPEN, first: 50) { totalCount nodes { number title isDraft reviewDecision mergeable
    commits(last: 1) { nodes { commit { statusCheckRollup { state } } } } } } } }"""


class GitHubProvider:
    def __init__(self, http):
        self.http = http

    def fetch(self, path, token):
        h = {'Accept': 'application/vnd.github+json'}
        if token:
            h['Authorization'] = f'Bearer {token}'
        repo, _ = self.http.get(f'{API}/repos/{path}', h)
        prs, pr_counts, pr_details, detail = self._pull_requests(path, token, h)
        runs, _ = self.http.get(f'{API}/repos/{path}/actions/runs?branch={repo["default_branch"]}&per_page=20', h)
        running, _ = self.http.get(f'{API}/repos/{path}/actions/runs?status=in_progress&per_page=1', h)
        ci_counts, ci_details, worst = summarize_ci(self._runs(runs['workflow_runs']), running['total_count'])
        return RepoStatus(name=repo['full_name'], url=repo['html_url'], prs=prs,
                          issues=repo['open_issues_count'] - prs,  # API count includes PRs
                          ci=worst, ci_counts=ci_counts, pr_counts=pr_counts, pr_detail=detail,
                          details={**{f'ci-{k}': v for k, v in ci_details.items()}, **pr_details})

    def _pull_requests(self, path, token, headers):
        """-> (total, bucket counts, details, has review detail). Review states need GraphQL, i.e. a token."""
        if token:
            owner, name = path.split('/', 1)
            data, _ = self.http.post(f'{API}/graphql', {'query': _PR_QUERY, 'variables': {'owner': owner, 'name': name}}, headers)
            prs = data['data']['repository']['pullRequests']
            counts, details = summarize_prs([(pr_bucket_github(n), f'#{n["number"]} {n["title"]}') for n in prs['nodes']])
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
