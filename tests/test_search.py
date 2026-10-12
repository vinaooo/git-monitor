import unittest

from painel.search import matches
from painel.status import RepoStatus


def status(**kw):
    return RepoStatus(name='api', url='https://github.com/acme/api', **kw)


class SearchTest(unittest.TestCase):
    def test_empty_query_matches_everything(self):
        self.assertTrue(matches('  ', 'github.com/a/b', 'b', None))

    def test_title_and_url_case_insensitive(self):
        s = status()
        self.assertTrue(matches('API', 'github.com/acme/api', 'My Service', s))
        self.assertTrue(matches('my serv', 'github.com/acme/api', 'My Service', s))
        self.assertTrue(matches('github.com/acme', 'github.com/acme/api', 'x', s))
        self.assertFalse(matches('zzz', 'github.com/acme/api', 'x', s))

    def test_ci_words(self):
        self.assertTrue(matches('passing', 'i', 't', status(ci_counts={'success': 2})))
        self.assertTrue(matches('failing', 'i', 't', status(ci_counts={'failure': 1})))
        self.assertFalse(matches('passing', 'i', 't', status(ci_counts={'failure': 1})))
        self.assertTrue(matches('no ci', 'i', 't', status()))

    def test_pr_words(self):
        s = status(pr_counts={'waiting': 1, 'approved': 1})
        self.assertTrue(matches('waiting', 'i', 't', s))
        self.assertTrue(matches('ready', 'i', 't', s))
        self.assertFalse(matches('conflict', 'i', 't', s))

    def test_all_words_must_match(self):
        s = status(pr_counts={'waiting': 1})
        self.assertTrue(matches('waiting api', 'i', 't', s))
        self.assertFalse(matches('waiting nope', 'i', 't', s))

    def test_no_status_yet_matches_identity_only(self):
        self.assertTrue(matches('acme', 'github.com/acme/api', 'api', None))
        self.assertFalse(matches('passing', 'github.com/acme/api', 'api', None))

    def test_error_text(self):
        self.assertTrue(matches('timeout', 'i', 't', RepoStatus(name='n', error='Network timeout')))
