from .status import RepoStatus

API = 'https://api.github.com'


class GitHubProvider:
    def __init__(self, http):
        self.http = http

    def fetch(self, path, token):
        h = {'Accept': 'application/vnd.github+json'}
        if token:
            h['Authorization'] = f'Bearer {token}'
        repo, _ = self.http.get(f'{API}/repos/{path}', h)
        search, _ = self.http.get(f'{API}/search/issues?q=repo:{path}+type:pr+state:open&per_page=1', h)
        runs, _ = self.http.get(f'{API}/repos/{path}/actions/runs?per_page=1', h)
        prs = search['total_count']
        return RepoStatus(name=repo['full_name'], url=repo['html_url'], prs=prs,
                          issues=repo['open_issues_count'] - prs,  # API count includes PRs
                          ci=self._ci(runs['workflow_runs']))

    @staticmethod
    def _ci(runs):
        if not runs:
            return 'none'
        if runs[0]['status'] != 'completed':
            return 'running'
        return runs[0]['conclusion'] or 'none'
