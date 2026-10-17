import unittest

from painel.ordering import move, shift_offsets, slot_at

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


TOPS = [0, 40, 80, 120]


class ShiftTest(unittest.TestCase):
    def test_slot_at_nearest_center(self):
        centers = [20, 60, 100, 140]
        self.assertEqual(slot_at(centers, -50), 0)
        self.assertEqual(slot_at(centers, 79), 1)
        self.assertEqual(slot_at(centers, 500), 3)

    def test_down_opens_gap_at_target(self):
        self.assertEqual(shift_offsets(TOPS, 0, 2), [80, -40, -40, 0])

    def test_up_pushes_rows_down(self):
        self.assertEqual(shift_offsets(TOPS, 3, 1), [0, 40, 40, -80])

    def test_same_slot_is_rest(self):
        self.assertEqual(shift_offsets(TOPS, 2, 2), [0, 0, 0, 0])
