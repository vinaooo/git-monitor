import unittest

from painel.cadence import Pace, next_delay


class NextDelayTest(unittest.TestCase):
    def test_default_is_the_base(self):
        self.assertEqual(next_delay(60, idle=0, errors=0), 60)

    def test_idle_groups_slow_down_in_two_steps_up_to_an_hour(self):
        self.assertEqual(next_delay(60, idle=3, errors=0), 120)
        self.assertEqual(next_delay(60, idle=6, errors=0), 240)
        self.assertEqual(next_delay(1800, idle=6, errors=0), 3600)

    def test_errors_back_off_exponentially_and_cap(self):
        self.assertEqual([next_delay(60, 0, e) for e in (1, 2, 3)], [120, 240, 480])
        self.assertEqual(next_delay(60, 0, 9), 900)
        self.assertEqual(next_delay(3600, 0, 2), 3600)  # never below the base

    def test_server_wait_is_a_floor(self):
        self.assertEqual(next_delay(60, 0, 0, wait=300.2), 301)
        self.assertEqual(next_delay(60, 0, 0, wait=5), 60)


class PaceTest(unittest.TestCase):
    def run_pass(self, pace, results):
        pace.begin(len(results))
        done = [pace.result(*r) for r in results]
        self.assertEqual(done, [False] * (len(results) - 1) + [True])

    def test_unchanged_passes_make_the_group_idle(self):
        pace = Pace()
        for _ in range(3):
            self.run_pass(pace, [(False, False, False), (False, False, False)])
        self.assertEqual(pace.idle, 3)
        self.assertEqual(pace.delay(60), 120)

    def test_a_change_or_running_ci_resets_idle(self):
        pace = Pace()
        for _ in range(3):
            self.run_pass(pace, [(False, False, False)])
        self.run_pass(pace, [(True, False, False)])
        self.assertEqual(pace.idle, 0)
        self.run_pass(pace, [(False, False, False)])
        self.run_pass(pace, [(False, True, False)])
        self.assertEqual(pace.idle, 0)

    def test_backoff_only_when_every_repo_failed(self):
        pace = Pace()
        self.run_pass(pace, [(False, False, True), (False, False, False)])
        self.assertEqual(pace.errors, 0)  # one dead repo must not slow the group forever
        self.run_pass(pace, [(False, False, True), (False, False, True)])
        self.assertEqual((pace.errors, pace.delay(60)), (1, 120))
        self.run_pass(pace, [(False, False, False)])
        self.assertEqual(pace.errors, 0)

    def test_results_outside_a_pass_are_ignored(self):
        pace = Pace()
        self.assertFalse(pace.result(True, True, True))  # fast-lane result, nobody called begin()
        self.assertEqual((pace.idle, pace.errors), (0, 0))

    def test_begin_zero_is_a_noop(self):
        pace = Pace()
        pace.begin(0)
        self.assertEqual(pace.idle, 0)


if __name__ == '__main__':
    unittest.main()
