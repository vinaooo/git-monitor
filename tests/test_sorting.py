import unittest

from painel.sorting import sorted_order
from painel.status import RepoStatus


def st(issues=0, prs=0, ci='none', error=None):
    return RepoStatus(name='x', issues=issues, prs=prs, ci=ci, error=error,
                      ci_counts={ci: 1} if ci != 'none' else {})


INFO = {'a': ('beta', st(issues=5, prs=1, ci='success')),
        'b': ('Alpha', st(issues=9, prs=1, ci='failure')),
        'c': ('gamma', st(issues=5, prs=7, ci='running')),
        'd': ('delta', None),                       # still loading
        'e': ('eps', st(error='Not found'))}        # fetch failed
ORDER = ['a', 'b', 'c', 'd', 'e']


class SortTest(unittest.TestCase):
    def sort(self, mode, reverse=False):
        return sorted_order(ORDER, mode, reverse, INFO)

    def test_manual_keeps_order(self):
        self.assertEqual(self.sort('manual'), ORDER)
        self.assertEqual(self.sort('manual', True), ORDER)

    def test_name_is_case_insensitive_and_unknowns_stay_sortable(self):
        self.assertEqual(self.sort('name'), ['b', 'a', 'd', 'e', 'c'])   # Alpha beta delta eps gamma
        self.assertEqual(self.sort('name', True), ['c', 'e', 'd', 'a', 'b'])

    def test_issues_most_first_ties_keep_manual_order(self):
        self.assertEqual(self.sort('issues'), ['b', 'a', 'c', 'd', 'e'])
        self.assertEqual(self.sort('issues', True), ['a', 'c', 'b', 'd', 'e'])  # fewest first, unknown last

    def test_prs(self):
        self.assertEqual(self.sort('prs'), ['c', 'a', 'b', 'd', 'e'])
        self.assertEqual(self.sort('prs', True), ['a', 'b', 'c', 'd', 'e'])

    def test_ci_failing_first(self):
        self.assertEqual(self.sort('ci'), ['b', 'c', 'a', 'd', 'e'])
        self.assertEqual(self.sort('ci', True), ['a', 'c', 'b', 'd', 'e'])

    def test_unknown_mode_falls_back_to_manual(self):
        self.assertEqual(self.sort('bogus'), ORDER)

    def test_does_not_mutate_input(self):
        order = list(ORDER)
        sorted_order(order, 'name', False, INFO)
        self.assertEqual(order, ORDER)
