import unittest

from painel.http import HttpError, NetworkError
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

    def test_unknown_host(self):
        self.assertIn('Unsupported', self.fetch(None, 'example.com/a/b').error)


class SecretHygieneTest(unittest.TestCase):
    def test_errors_never_contain_token(self):
        for err in (NetworkError('boom'), HttpError(403), KeyError('x')):
            s = StatusService(FakeHttp(error=err)).fetch('github.com/o/r', 's3cret-token')
            self.assertNotIn('s3cret-token', s.error)

    def test_gitlab_uses_https_and_own_host(self):
        http = FakeHttp(error=HttpError(404))
        StatusService(http).fetch('gitlab.example.org/a/b', 'tok')
        self.assertTrue(all(u.startswith('https://gitlab.example.org/') for u in http.urls))
