import json
import os
import tempfile
import unittest

from painel.notify import StateStore, ci_url, step, wanted


def seen(ci, settled=None):
    return {'ci': ci, 'settled': settled or (ci if ci in ('success', 'failure') else 'none')}


class StepTest(unittest.TestCase):
    def test_first_sight_is_silent_and_recorded(self):
        entry, kind = step(None, 'failure')
        self.assertEqual((entry, kind), (seen('failure'), None))

    def test_failed(self):
        self.assertEqual(step(seen('success'), 'failure')[1], 'failed')

    def test_recovered(self):
        self.assertEqual(step(seen('failure'), 'success')[1], 'recovered')

    def test_running_to_failure(self):
        self.assertEqual(step(seen('running', 'success'), 'failure')[1], 'broke_running')

    def test_recovery_survives_a_running_phase(self):
        entry, kind = step(seen('failure'), 'running')
        self.assertEqual((entry['settled'], kind), ('failure', None))
        self.assertEqual(step(entry, 'success')[1], 'recovered')

    def test_still_failing_after_rerun_is_silent(self):
        entry, _ = step(seen('failure'), 'running')
        self.assertIsNone(step(entry, 'failure')[1])

    def test_unchanged_and_cancelled_are_silent(self):
        self.assertIsNone(step(seen('success'), 'success')[1])
        entry, kind = step(seen('success'), 'cancelled')
        self.assertEqual((entry['settled'], kind), ('success', None))

    def test_running_from_unknown_to_failure(self):
        self.assertEqual(step(seen('running', 'none'), 'failure')[1], 'broke_running')


class HelpersTest(unittest.TestCase):
    def test_wanted(self):
        self.assertTrue(wanted('failed', ['failed']))
        self.assertFalse(wanted('recovered', ['failed']))
        self.assertFalse(wanted(None, ['failed']))

    def test_ci_url(self):
        self.assertEqual(ci_url('https://github.com/o/r'), 'https://github.com/o/r/actions')
        self.assertEqual(ci_url('https://gitlab.com/g/p'), 'https://gitlab.com/g/p/-/pipelines')
        self.assertEqual(ci_url(''), '')


class StateStoreTest(unittest.TestCase):
    def test_roundtrip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'sub', 'ci.json')
            self.assertEqual(StateStore(path).data, {})
            store = StateStore(path)
            store.data['a'] = seen('success')
            store.save()
            self.assertEqual(StateStore(path).data, {'a': seen('success')})

    def test_corrupt_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'ci.json')
            open(path, 'w').write('{nope')
            self.assertEqual(StateStore(path).data, {})
            json.dumps(StateStore(path).data)

    def test_forget(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(os.path.join(d, 'ci.json'))
            store.data['a'] = seen('success')
            store.forget('a')
            self.assertEqual(StateStore(store.path).data, {})


if __name__ == '__main__':
    unittest.main()
