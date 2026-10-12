import unittest

from painel.icons import CHOICES, DEFAULT, IconStore
from painel.virtual import DEFINITIONS


class IconStoreTest(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.store = IconStore({'Work': 'computer-symbolic'}, self.saved.append)

    def test_default_when_unset(self):
        self.assertEqual(self.store.get('Nope'), DEFAULT)
        self.assertEqual(self.store.get('Work'), 'computer-symbolic')

    def test_set_and_reset_to_default(self):
        self.store.set('Home', 'go-home-symbolic')
        self.assertEqual(self.saved[-1], {'Work': 'computer-symbolic', 'Home': 'go-home-symbolic'})
        self.store.set('Home', DEFAULT)  # default is not stored
        self.assertEqual(self.saved[-1], {'Work': 'computer-symbolic'})

    def test_rename_and_remove(self):
        self.store.rename_group('Work', 'Job')
        self.assertEqual(self.store.get('Job'), 'computer-symbolic')
        self.assertEqual(self.store.get('Work'), DEFAULT)
        self.store.remove_group('Job')
        self.assertEqual(self.saved[-1], {})

    def test_choices_are_unique_and_include_default(self):
        self.assertEqual(len(CHOICES), len(set(CHOICES)))
        self.assertIn(DEFAULT, CHOICES)

    def test_every_virtual_group_has_an_icon(self):
        for d in DEFINITIONS:
            self.assertTrue(d.icon.endswith('-symbolic'), d.id)


if __name__ == '__main__':
    unittest.main()
