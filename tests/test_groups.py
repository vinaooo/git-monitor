import unittest

from painel.groups import Groups


class GroupsTest(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.g = Groups([('Work', ['a', 'b']), ('Home', ['c'])], self.saved.append)

    def test_queries(self):
        self.assertEqual(self.g.names(), ['Work', 'Home'])
        self.assertEqual(self.g.repos('Work'), ['a', 'b'])
        self.assertEqual(self.g.all_repos(), ['a', 'b', 'c'])
        self.assertEqual(self.g.group_of('c'), 'Home')
        self.assertIsNone(self.g.group_of('zzz'))

    def test_migrates_legacy_repos_into_general(self):
        g = Groups([], self.saved.append, legacy_repos=['x', 'y'])
        self.assertEqual(g.names(), ['General'])
        self.assertEqual(g.repos('General'), ['x', 'y'])

    def test_always_at_least_one_group(self):
        self.assertEqual(Groups([], lambda s: None).names(), ['General'])

    def test_add_group_normalizes_and_rejects(self):
        self.assertEqual(self.g.add_group('  Play '), 'Play')
        self.assertIsNone(self.g.add_group('   '))
        self.assertIsNone(self.g.add_group('work'))  # case-insensitive duplicate
        self.assertEqual(self.g.names(), ['Work', 'Home', 'Play'])

    def test_rename(self):
        self.assertTrue(self.g.rename('Work', 'Job'))
        self.assertEqual(self.g.repos('Job'), ['a', 'b'])
        self.assertFalse(self.g.rename('Job', 'home'))   # duplicate
        self.assertFalse(self.g.rename('Job', ' '))
        self.assertFalse(self.g.rename('nope', 'X'))
        self.assertTrue(self.g.rename('Job', 'job'))      # case-only change of itself is fine

    def test_remove_returns_repos_and_keeps_last(self):
        self.assertEqual(self.g.remove('Work'), ['a', 'b'])
        self.assertFalse(self.g.can_remove('Home'))        # last one
        with self.assertRaises(ValueError):
            self.g.remove('Home')

    def test_repo_mutations(self):
        self.g.add_repo('Home', 'd')
        self.g.move_repo('a', 'Home')
        self.assertEqual(self.g.repos('Home'), ['c', 'd', 'a'])
        self.assertEqual(self.g.repos('Work'), ['b'])
        self.g.remove_repo('d')
        self.assertEqual(self.g.repos('Home'), ['c', 'a'])

    def test_add_repo_is_unique_across_groups(self):
        self.g.add_repo('Home', 'a')  # already in Work
        self.assertEqual(self.g.repos('Home'), ['c'])

    def test_set_order_only_accepts_same_members(self):
        self.g.set_order('Work', ['b', 'a'])
        self.assertEqual(self.g.repos('Work'), ['b', 'a'])
        self.g.set_order('Work', ['b', 'x'])
        self.assertEqual(self.g.repos('Work'), ['b', 'a'])

    def test_set_group_order(self):
        self.g.set_group_order(['Home', 'Work'])
        self.assertEqual(self.g.names(), ['Home', 'Work'])
        self.g.set_group_order(['Home'])  # missing member: ignored
        self.assertEqual(self.g.names(), ['Home', 'Work'])

    def test_every_mutation_saves_a_copy(self):
        self.g.add_repo('Home', 'd')
        self.assertEqual(self.saved[-1], [('Work', ['a', 'b']), ('Home', ['c', 'd'])])
        self.saved[-1][0][1].append('mutated')
        self.assertEqual(self.g.repos('Work'), ['a', 'b'])

    def test_persist_saves_current_state(self):
        g = Groups([], self.saved.append, legacy_repos=['x'])
        g.persist()
        self.assertEqual(self.saved[-1], [('General', ['x'])])
