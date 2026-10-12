import unittest

from painel.rate_limit import github_warning, github_warning_groups, min_interval


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


class GroupsWarningTest(unittest.TestCase):
    def test_sums_every_group_at_its_own_interval(self):
        # 10*3*(3600/60) + 20*3*(3600/300) = 2520 requests/hour
        self.assertIsNone(github_warning_groups([(10, 60), (20, 300)], True))
        self.assertIn('~10800', github_warning_groups([(20, 30), (20, 60)], True))

    def test_one_slow_group_does_not_hide_a_fast_one(self):
        self.assertIn('5000', github_warning_groups([(87, 60), (1, 3600)], True))

    def test_matches_the_single_group_form(self):
        self.assertEqual(github_warning_groups([(30, 15)], True), github_warning(15, 30, True))


class MinIntervalTest(unittest.TestCase):
    def test_rounds_up_to_5_seconds(self):
        self.assertEqual(min_interval(87, True), 190)  # 87*3*3600/5000 = 187.9

    def test_never_below_15_seconds(self):
        self.assertEqual(min_interval(1, True), 15)
        self.assertEqual(min_interval(0, False), 15)

    def test_anonymous_budget_is_much_smaller(self):
        self.assertEqual(min_interval(1, False), 240)

    def test_capped_at_an_hour(self):
        self.assertEqual(min_interval(100, False), 3600)

    def test_the_suggestion_fits_the_limit(self):
        for repos in (1, 10, 87, 400):
            self.assertIsNone(github_warning(min_interval(repos, True), repos, True), repos)
