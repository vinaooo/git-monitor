import unittest

from painel.gitlab import GitLabProvider
from tests.fakes import FakeHttp


def routes(pipes, total='4'):
    return {'/merge_requests': ([], {'X-Total': total}),
            '/issues_statistics': ({'statistics': {'counts': {'opened': 9}}}, {}),
            '/pipelines': (pipes, {}),
            '/projects/g%2Fsub%2Fp': ({'name_with_namespace': 'G / Sub / P',
                                       'web_url': 'https://gitlab.com/g/sub/p'}, {})}


class GitLabTest(unittest.TestCase):
    def fetch(self, pipes, token=None, total='4'):
        http = FakeHttp(routes(pipes, total))
        return GitLabProvider('gitlab.com', http).fetch('g/sub/p', token), http

    def test_counts_and_name(self):
        s, http = self.fetch([])
        self.assertEqual((s.name, s.url, s.issues, s.prs, s.ci), ('G/Sub/P', 'https://gitlab.com/g/sub/p', 9, 4, 'none'))
        self.assertTrue(http.urls[0].startswith('https://gitlab.com/api/v4/projects/g%2Fsub%2Fp'))

    def test_missing_total_header_is_zero(self):
        self.assertEqual(self.fetch([], total='')[0].prs, 0)

    def test_pipeline_mapping(self):
        for gl, ci in (('failed', 'failure'), ('canceled', 'cancelled'), ('success', 'success'),
                       ('running', 'running'), ('pending', 'running'), ('skipped', 'none')):
            self.assertEqual(self.fetch([{'status': gl}])[0].ci, ci, gl)

    def test_token_header(self):
        _, http = self.fetch([], token='tok')
        self.assertTrue(all(h['PRIVATE-TOKEN'] == 'tok' for h in http.sent))
