import unittest

from painel.ordering import deltas


class DeltasTest(unittest.TestCase):
    def test_offset_is_old_minus_new(self):
        self.assertEqual(deltas({'a': (0, 0), 'b': (100, 0)}, {'a': (100, 0), 'b': (0, 0)}),
                         {'a': (-100, 0), 'b': (100, 0)})

    def test_unmoved_and_tiny_moves_omitted(self):
        self.assertEqual(deltas({'a': (5, 5), 'b': (1, 1)}, {'a': (5, 5), 'b': (1.2, 1)}), {})

    def test_ignores_items_missing_on_either_side(self):
        self.assertEqual(deltas({'a': (0, 0), 'gone': (1, 1)}, {'a': (0, 10), 'new': (2, 2)}),
                         {'a': (0, -10)})
