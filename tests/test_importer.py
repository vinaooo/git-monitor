import unittest

from painel.importer import group_name, plan, select
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
