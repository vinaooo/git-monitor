import unittest

from painel.ordering import move

ABCD = ['a', 'b', 'c', 'd']


class MoveTest(unittest.TestCase):
    def test_forward_lands_after_target_slot(self):
        self.assertEqual(move(ABCD, 'a', 'c'), ['b', 'c', 'a', 'd'])

    def test_backward_lands_before_target(self):
        self.assertEqual(move(ABCD, 'd', 'b'), ['a', 'd', 'b', 'c'])

    def test_to_ends(self):
        self.assertEqual(move(ABCD, 'a', 'd'), ['b', 'c', 'd', 'a'])
        self.assertEqual(move(ABCD, 'd', 'a'), ['d', 'a', 'b', 'c'])

    def test_noop_cases(self):
        self.assertEqual(move(ABCD, 'b', 'b'), ABCD)
        self.assertEqual(move(ABCD, 'x', 'b'), ABCD)
        self.assertEqual(move(ABCD, 'b', 'x'), ABCD)

    def test_does_not_mutate_input(self):
        src = list(ABCD)
        move(src, 'a', 'c')
        self.assertEqual(src, ABCD)
