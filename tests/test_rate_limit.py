import unittest

from painel.rate_limit import github_warning


class RateLimitTest(unittest.TestCase):
    def test_anonymous_over_limit_warns(self):
        # 1 repo * 4 calls * 3600/60s = 240/h > 60/h
        self.assertIn('60', github_warning(60, 1, False))

    def test_anonymous_within_limit(self):
        self.assertIsNone(github_warning(240, 1, False))  # exactly 60/h

    def test_below_60s_always_warns_anonymous(self):
        self.assertIsNotNone(github_warning(59, 1, False))

    def test_token_raises_limit(self):
        self.assertIsNone(github_warning(15, 1, True))  # 3 REST calls: 720/h < 5000
        self.assertIn('5000', github_warning(15, 30, True))

    def test_no_github_repos_no_warning(self):
        self.assertIsNone(github_warning(15, 0, False))
