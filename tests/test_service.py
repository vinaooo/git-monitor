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
