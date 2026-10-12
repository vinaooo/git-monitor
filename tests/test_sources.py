import unittest

from painel.sources import SourceStore


class SourceStoreTest(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.store = SourceStore([], self.saved.append)

    def test_add_records_the_source_and_persists(self):
        self.store.add('Me', 'github.com', 'me', ['forks'], ['github.com/me/a'])
        self.assertEqual(self.store.all(), [('Me', 'github.com', 'me', ['forks'])])
        self.assertEqual(self.saved[-1], [('Me', 'github.com', 'me', ['forks'], ['github.com/me/a'])])

    def test_loads_persisted_records(self):
        store = SourceStore([('Me', 'github.com', 'me', [], ['github.com/me/a'])], self.saved.append)
        self.assertEqual(store.all(), [('Me', 'github.com', 'me', [])])

    def test_adding_again_keeps_what_was_already_known(self):
        self.store.add('Me', 'github.com', 'me', [], ['github.com/me/a'])
        self.store.add('Me', 'github.com', 'me', ['forks'], ['github.com/me/b'])
        self.assertEqual(self.saved[-1], [('Me', 'github.com', 'me', ['forks'], ['github.com/me/a', 'github.com/me/b'])])

    def test_take_new_returns_unseen_once_and_remembers_them(self):
        self.store.add('Me', 'github.com', 'me', [], ['github.com/me/a'])
        self.assertEqual(self.store.take_new('Me', ['github.com/me/a', 'github.com/Me/B']), ['github.com/Me/B'])
        self.assertEqual(self.store.take_new('Me', ['github.com/me/a', 'github.com/me/b']), [])  # case-insensitive

    def test_a_card_the_user_removed_is_not_resurrected(self):
        self.store.add('Me', 'github.com', 'me', [], ['github.com/me/a'])  # a was imported, then removed by the user
        self.assertEqual(self.store.take_new('Me', ['github.com/me/a']), [])

    def test_unknown_group(self):
        self.assertEqual(self.store.take_new('Nope', ['x']), [])

    def test_rename_and_remove_group(self):
        self.store.add('Me', 'github.com', 'me', [], [])
        self.store.rename_group('Me', 'Mine')
        self.assertEqual([s[0] for s in self.store.all()], ['Mine'])
        self.store.remove_group('Mine')
        self.assertEqual(self.store.all(), [])
        self.assertEqual(self.saved[-1], [])
