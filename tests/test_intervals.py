import unittest

from painel.intervals import IntervalStore


class IntervalStoreTest(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.store = IntervalStore({'Big': 300}, self.saved.append)

    def test_get_and_effective_fall_back_to_the_default(self):
        self.assertEqual(self.store.get('Big'), 300)
        self.assertIsNone(self.store.get('Small'))
        self.assertEqual(self.store.effective('Big', 60), 300)
        self.assertEqual(self.store.effective('Small', 60), 60)

    def test_set_persists_and_none_means_default(self):
        self.store.set('Small', 120)
        self.assertEqual(self.saved[-1], {'Big': 300, 'Small': 120})
        self.store.set('Big', None)
        self.assertEqual(self.saved[-1], {'Small': 120})
        self.assertIsNone(self.store.get('Big'))

    def test_set_clamps_to_the_row_bounds(self):
        self.store.set('A', 5)
        self.store.set('B', 99999)
        self.assertEqual((self.store.get('A'), self.store.get('B')), (15, 3600))

    def test_rename_and_remove_group(self):
        self.store.rename_group('Big', 'Huge')
        self.assertEqual(self.saved[-1], {'Huge': 300})
        self.store.remove_group('Huge')
        self.assertEqual(self.saved[-1], {})

    def test_unknown_group_changes_nothing(self):
        n = len(self.saved)
        self.store.rename_group('Nope', 'X')
        self.store.remove_group('Nope')
        self.assertEqual(len(self.saved), n)
