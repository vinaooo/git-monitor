import unittest

from painel.github import GitHubProvider
from tests.fakes import FakeHttp


def routes(runs):
    return {'/search/issues': ({'total_count': 3}, {}),
            '/actions/runs': ({'workflow_runs': runs}, {}),
            '/repos/o/r': ({'full_name': 'O/r', 'html_url': 'https://github.com/O/r',
                            'open_issues_count': 10}, {})}


class GitHubTest(unittest.TestCase):
    def fetch(self, runs, token=None):
        http = FakeHttp(routes(runs))
        return GitHubProvider(http).fetch('o/r', token), http

    def test_issues_exclude_prs(self):
        s, _ = self.fetch([])
        self.assertEqual((s.name, s.url, s.issues, s.prs, s.ci), ('O/r', 'https://github.com/O/r', 7, 3, 'none'))

    def test_ci_states(self):
        self.assertEqual(self.fetch([{'status': 'in_progress', 'conclusion': None}])[0].ci, 'running')
        self.assertEqual(self.fetch([{'status': 'completed', 'conclusion': 'success'}])[0].ci, 'success')
        self.assertEqual(self.fetch([{'status': 'completed', 'conclusion': 'failure'}])[0].ci, 'failure')
        self.assertEqual(self.fetch([{'status': 'completed', 'conclusion': None}])[0].ci, 'none')

    def test_token_sent_as_bearer(self):
        _, http = self.fetch([], token='tok')
        self.assertTrue(all(h['Authorization'] == 'Bearer tok' for h in http.sent))
