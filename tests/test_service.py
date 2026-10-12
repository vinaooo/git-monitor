import unittest

from painel.http import CachingClient, HttpError, NetworkError, RateState
from painel.service import StatusService
from tests.fakes import FakeHttp


class ServiceTest(unittest.TestCase):
    def fetch(self, error, ident='github.com/o/r'):
        return StatusService(FakeHttp(error=error)).fetch(ident, None)

    def test_http_errors_become_messages(self):
        self.assertIn('Not found', self.fetch(HttpError(404)).error)
        self.assertIn('Invalid token', self.fetch(HttpError(401)).error)
        self.assertIn('rate limited', self.fetch(HttpError(403)).error.lower())
        self.assertEqual(self.fetch(HttpError(500)).error, 'HTTP 500')

    def test_network_error(self):
        self.assertIn('Network error', self.fetch(NetworkError('down')).error)

    def test_malformed_payload(self):
        http = FakeHttp({'/search/issues': ({'total_count': 0}, {}), '/actions/runs': ({'workflow_runs': []}, {}), '/repos/o/r': ({}, {})})
        self.assertEqual(StatusService(http).fetch('github.com/o/r', None).error, 'Unexpected API response')

    def test_error_keeps_repo_path_as_name(self):
        self.assertEqual(self.fetch(HttpError(404)).name, 'o/r')

    def test_review_requests_failure_is_empty(self):
        self.assertEqual(StatusService(FakeHttp(error=HttpError(403))).review_requests('github.com', 'tok'), set())

    def test_unknown_host(self):
        self.assertIn('Unsupported', self.fetch(None, 'example.com/a/b').error)


class ListReposTest(unittest.TestCase):
    def list(self, http, host='github.com'):
        return StatusService(http).list_repos(host, 'o', None)

    def test_returns_repos_and_truncated_flag(self):
        http = FakeHttp({'/users/o/repos': ([{'full_name': 'o/a', 'fork': False, 'archived': False, 'private': False}], {})})
        infos, truncated, error = self.list(http)
        self.assertEqual(([i.path for i in infos], truncated, error), (['o/a'], False, None))

    def test_errors_become_messages(self):
        self.assertIn('Not found', self.list(FakeHttp(error=HttpError(404)))[2])
        self.assertIn('Network error', self.list(FakeHttp(error=NetworkError('down')))[2])
        self.assertEqual(self.list(FakeHttp(error=HttpError(500)))[2], 'HTTP 500')
        self.assertEqual(self.list(FakeHttp({'/users/o/repos': ([{}], {})}))[2], 'Unexpected API response')

    def test_unsupported_host(self):
        self.assertIn('Unsupported host', self.list(FakeHttp(), 'example.com')[2])


class SecretHygieneTest(unittest.TestCase):
    def test_errors_never_contain_token(self):
        for err in (NetworkError('boom'), HttpError(403), KeyError('x')):
            s = StatusService(FakeHttp(error=err)).fetch('github.com/o/r', 's3cret-token')
            self.assertNotIn('s3cret-token', s.error)

    def test_forgejo_uses_https_and_own_host(self):
        http = FakeHttp(error=HttpError(404))
        s = StatusService(http).fetch('codeberg.org/a/b', 'tok')
        self.assertTrue(all(u.startswith('https://codeberg.org/api/v1/') for u in http.urls))
        self.assertEqual((s.error, StatusService.batch_size('codeberg.org', 'tok')), ('Not found (private? add a token)', 0))

    def test_gitlab_uses_https_and_own_host(self):
        http = FakeHttp(error=HttpError(404))
        StatusService(http).fetch('gitlab.example.org/a/b', 'tok')
        self.assertTrue(all(u.startswith('https://gitlab.example.org/') for u in http.urls))


class BatchTest(unittest.TestCase):
    def gql(self):
        r = {'nameWithOwner': 'o/r', 'url': 'u', 'issues': {'totalCount': 1}, 'defaultBranchRef': {'name': 'main'},
             'pullRequests': {'totalCount': 0, 'nodes': []}}
        return FakeHttp({'/graphql': ({'data': {'r0': r}}, {})})

    def test_batching_only_for_github_with_a_token(self):
        svc = StatusService(FakeHttp())
        self.assertEqual(svc.batch_size('github.com', 'tok'), 10)
        self.assertEqual(svc.batch_size('github.com', None), 0)
        self.assertEqual(svc.batch_size('gitlab.com', 'tok'), 0)

    def test_heads_keyed_by_ident(self):
        heads = StatusService(self.gql()).heads(['github.com/o/r'], 'tok')
        self.assertEqual(heads['github.com/o/r'].branch, 'main')

    def test_failed_batch_is_empty_so_every_repo_falls_back(self):
        self.assertEqual(StatusService(FakeHttp(error=HttpError(502))).heads(['github.com/o/r'], 'tok'), {})
        self.assertEqual(StatusService(FakeHttp({'/graphql': ({'data': None}, {})})).heads(['github.com/o/r'], 'tok'),
                         {'github.com/o/r': None})

    def test_fetch_uses_the_head(self):
        http = FakeHttp({'/graphql': self.gql().routes['/graphql'], 'status=in_progress': ({'total_count': 0}, {}),
                         'branch=main': ({'workflow_runs': []}, {})})
        svc = StatusService(http)
        head = svc.heads(['github.com/o/r'], 'tok')['github.com/o/r']
        self.assertEqual(svc.fetch('github.com/o/r', 'tok', head).name, 'o/r')
        self.assertEqual(len([u for u in http.urls if '/graphql' not in u]), 2)

    def test_wait_and_ratio_default_to_nothing_without_a_caching_client(self):
        svc = StatusService(FakeHttp())
        self.assertEqual((svc.wait('github.com'), svc.not_modified_ratio()), (0, 0.0))

    def test_wait_and_ratio_come_from_the_caching_client(self):
        client = CachingClient(FakeHttp(), RateState(clock=lambda: 10))
        client.state.note('https://api.github.com/x', {'Retry-After': '30'})
        svc = StatusService(client)
        self.assertEqual(svc.wait('github.com'), 30)  # ident host -> API host
