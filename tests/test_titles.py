import unittest

from painel.titles import TitleStore


class TitleStoreTest(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.store = TitleStore({'github.com/a/b': 'Mine'}, self.saved.append)

    def test_get(self):
        self.assertEqual(self.store.get('github.com/a/b'), 'Mine')
        self.assertIsNone(self.store.get('github.com/x/y'))

    def test_set_strips_and_saves(self):
        self.store.set('github.com/x/y', '  Work  ')
        self.assertEqual(self.store.get('github.com/x/y'), 'Work')
        self.assertEqual(self.saved[-1], {'github.com/a/b': 'Mine', 'github.com/x/y': 'Work'})

    def test_blank_restores_default(self):
        self.store.set('github.com/a/b', '   ')
        self.assertIsNone(self.store.get('github.com/a/b'))
        self.assertEqual(self.saved[-1], {})

    def test_remove_forgets_title(self):
        self.store.remove('github.com/a/b')
        self.assertEqual(self.saved[-1], {})
        self.store.remove('github.com/unknown')  # no-op, no extra save
        self.assertEqual(len(self.saved), 1)

    def test_save_receives_copy(self):
        self.store.set('github.com/x/y', 'T')
        self.saved[-1]['github.com/x/y'] = 'mutated'
        self.assertEqual(self.store.get('github.com/x/y'), 'T')
