import urllib.parse

from .health import pr_bucket_gitlab, summarize_ci, summarize_prs
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
        mrs, hdr = self.http.get(f'{base}/merge_requests?state=opened&per_page=50', h)
        stats, _ = self.http.get(f'{base}/issues_statistics', h)  # project payload omits the count when anonymous
        branch = urllib.parse.quote(project.get('default_branch') or 'main', safe='')
        pipes, _ = self.http.get(f'{base}/pipelines?ref={branch}&per_page=20', h)
        # listing (not X-Total): counting running pipelines server-side times out on huge projects
        running, _ = self.http.get(f'{base}/pipelines?status=running&per_page=100', h)
        pr_counts, pr_details = summarize_prs([(pr_bucket_gitlab(m), f'!{m["iid"]} {m["title"]}') for m in mrs])
        ci_counts, ci_details, worst = summarize_ci(
            [{'key': p.get('source'), 'state': _CI.get(p['status'], 'ignored'), 'label': f'#{p["id"]} {p.get("source", "")}'}
             for p in pipes], len(running))
        return RepoStatus(name=project['name_with_namespace'].replace(' / ', '/'), url=project['web_url'],
                          prs=int(hdr.get('X-Total') or 0),  # header omitted above 10000 results
                          issues=stats['statistics']['counts']['opened'],
                          ci=worst, ci_counts=ci_counts, pr_counts=pr_counts,
                          details={**{f'ci-{k}': v for k, v in ci_details.items()}, **pr_details})
