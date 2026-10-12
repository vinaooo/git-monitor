import unittest

from painel.importer import default_selection, group_name, plan, select, wanted
from painel.status import RepoInfo

A, FORK, OLD, PRIV = RepoInfo('me/a', False, False, False), RepoInfo('me/f', True, False, False), \
    RepoInfo('me/o', False, True, False), RepoInfo('me/p', False, False, True)
ALL = [A, FORK, OLD, PRIV]


class GroupNameTest(unittest.TestCase):
    def test_capitalizes_the_last_path_segment(self):
        self.assertEqual(group_name('vinaooo'), 'Vinaooo')
        self.assertEqual(group_name('group/sub'), 'Sub')
        self.assertEqual(group_name('McMurdo'), 'McMurdo')


class SelectTest(unittest.TestCase):
    def test_kinds_are_opt_in_and_private_is_always_kept(self):
        self.assertEqual(select(ALL, forks=False, archived=False), [A, PRIV])
        self.assertEqual(select(ALL, forks=True, archived=False), [A, FORK, PRIV])
        self.assertEqual(select(ALL, forks=False, archived=True), [A, OLD, PRIV])
        self.assertEqual(select(ALL, forks=True, archived=True), ALL)


class PlanTest(unittest.TestCase):
    def test_new_idents_get_the_host_and_tracked_ones_are_counted(self):
        new, tracked = plan(ALL, 'github.com', False, False, ['github.com/me/a', 'github.com/other/x'])
        self.assertEqual((new, tracked), (['github.com/me/p'], 1))

    def test_tracked_match_ignores_case(self):
        self.assertEqual(plan([A], 'github.com', False, False, ['github.com/ME/A']), ([], 1))

    def test_nothing_selected(self):
        self.assertEqual(plan([], 'github.com', True, True, []), ([], 0))


class WantedTest(unittest.TestCase):
    def test_a_repo_must_pass_every_kind_it_belongs_to(self):
        both = RepoInfo('me/x', True, True, False)
        self.assertFalse(wanted(both, forks=True, archived=False))
        self.assertFalse(wanted(both, forks=False, archived=True))
        self.assertTrue(wanted(both, forks=True, archived=True))
        self.assertTrue(wanted(A, forks=False, archived=False))


class DefaultSelectionTest(unittest.TestCase):
    def test_is_the_set_of_new_idents_the_plan_would_import(self):
        picked = default_selection(ALL, 'github.com', False, False, ['github.com/me/a'])
        self.assertEqual(picked, {'github.com/me/p'})

    def test_tracked_repos_are_never_preselected(self):
        self.assertEqual(default_selection([A], 'github.com', True, True, ['github.com/ME/A']), set())
