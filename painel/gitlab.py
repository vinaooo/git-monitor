import urllib.parse

from .status import RepoStatus

_CI = {'success': 'success', 'failed': 'failure', 'canceled': 'cancelled',
       'running': 'running', 'pending': 'running', 'created': 'running', 'preparing': 'running',
       'waiting_for_resource': 'running', 'scheduled': 'running'}


class GitLabProvider:
    def __init__(self, host, http):
        self.host, self.http = host, http

    def fetch(self, path, token):
        h = {'PRIVATE-TOKEN': token} if token else {}
        base = f'https://{self.host}/api/v4/projects/{urllib.parse.quote(path, safe="")}'
        project, _ = self.http.get(base, h)
        _, hdr = self.http.get(f'{base}/merge_requests?state=opened&per_page=1', h)
        stats, _ = self.http.get(f'{base}/issues_statistics', h)  # project payload omits the count when anonymous
        pipes, _ = self.http.get(f'{base}/pipelines?per_page=1', h)
        return RepoStatus(name=project['name_with_namespace'].replace(' / ', '/'), url=project['web_url'],
                          prs=int(hdr.get('X-Total') or 0),  # header omitted above 10000 results
                          issues=stats['statistics']['counts']['opened'],
                          ci=_CI.get(pipes[0]['status'], 'none') if pipes else 'none')
