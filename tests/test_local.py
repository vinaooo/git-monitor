import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone

from painel import local
from painel.search import matches
from painel.status import RepoStatus

ENV = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't',
       'GIT_COMMITTER_EMAIL': 't@t', 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}


def git(cwd, *args):
    subprocess.run(['git', *args], cwd=cwd, env=ENV, check=True, capture_output=True)


def commit(cwd, name):
    with open(os.path.join(cwd, name), 'w') as f:
        f.write(name)
    git(cwd, 'add', name)
    git(cwd, 'commit', '-qm', name)


class ParseTest(unittest.TestCase):
    def test_full(self):
        s = local.parse_status('# branch.oid abcdef1234\n# branch.head main\n# branch.upstream origin/main\n'
                               '# branch.ab +2 -3\n1 .M N... 100644 100644 100644 a b f.py\n'
                               'u UU N... 1 2 3 4 a b c g.py\n? new.txt\n? n2.txt\n! ignored\n')
        self.assertEqual((s.branch, s.upstream, s.ahead, s.behind, s.dirty, s.untracked), ('main', 'origin/main', 2, 3, 2, 2))

    def test_detached_no_upstream(self):
        s = local.parse_status('# branch.oid abcdef1234\n# branch.head (detached)\n')
        self.assertEqual((s.branch, s.oid, s.upstream, s.ahead), (None, 'abcdef1', None, None))

    def test_origin_matches(self):
        for url in ('https://github.com/o/r.git', 'git@github.com:o/r.git', 'ssh://git@github.com:22/o/r', 'https://user@github.com/O/R/'):
            self.assertTrue(local.origin_matches(url, 'github.com/o/r'), url)
        self.assertTrue(local.origin_matches('git@gitlab.com:g/sub/p.git', 'gitlab.com/g/sub/p'))
        self.assertFalse(local.origin_matches('https://github.com/o/other', 'github.com/o/r'))

    def test_only_read_only_git(self):
        with self.assertRaises(AssertionError):
            local.run_git(('fetch',), '.')


class FakeRunTest(unittest.TestCase):
    def test_missing_folder(self):
        self.assertEqual(local.inspect('/nonexistent/x').error, 'missing')

    def test_no_git_binary_and_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, '.git'))
            def nogit(*_): raise FileNotFoundError
            def slow(*_): raise subprocess.TimeoutExpired('git', 1)
            self.assertEqual(local.inspect(d, nogit).error, 'nogit')
            self.assertEqual(local.inspect(d, slow).error, 'timeout')

    def test_worktree_file_unsupported(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, '.git'), 'w') as f:
                f.write('gitdir: /elsewhere')
            self.assertEqual(local.inspect(d).error, 'unsupported')


@unittest.skipUnless(subprocess.run(['git', '--version'], capture_output=True).returncode == 0, 'needs git')
class RealRepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        self.remote, self.clone = os.path.join(root, 'remote.git'), os.path.join(root, 'clone')
        self.other = os.path.join(root, 'other')
        git(root, 'init', '-q', '--bare', '-b', 'main', 'remote.git')
        git(root, 'clone', '-q', 'remote.git', 'clone')
        commit(self.clone, 'a')
        git(self.clone, 'push', '-q', '-u', 'origin', 'main')
        git(self.clone, 'remote', 'set-head', 'origin', 'main')
        git(self.clone, 'fetch', '-q')
        git(root, 'clone', '-q', 'remote.git', 'other')

    def push_from_other(self):
        commit(self.other, 'b' + str(len(os.listdir(self.other))))
        git(self.other, 'push', '-q')
        git(self.clone, 'fetch', '-q')

    def test_clean(self):
        s = local.inspect(self.clone)
        self.assertEqual((s.branch, s.default_branch, s.ahead, s.behind, s.dirty, s.untracked, s.error),
                         ('main', 'main', 0, 0, 0, 0, None))
        self.assertIsNotNone(s.fetched_at)
        self.assertIn('✓ clean', [c.text for c in local.chips(s)])

    def test_dirty_and_untracked(self):
        with open(os.path.join(self.clone, 'a'), 'w') as f:
            f.write('changed')
        open(os.path.join(self.clone, 'new'), 'w').close()
        s = local.inspect(self.clone)
        self.assertEqual((s.dirty, s.untracked), (1, 1))
        self.assertIn('dirty', local.words(s))

    def test_ahead(self):
        commit(self.clone, 'c')
        s = local.inspect(self.clone)
        self.assertEqual((s.ahead, s.behind), (1, 0))

    def test_behind_uses_last_fetch_only(self):
        commit(self.other, 'b')
        git(self.other, 'push', '-q')
        self.assertEqual(local.inspect(self.clone).behind, 0)  # remote moved, clone not fetched: not live
        git(self.clone, 'fetch', '-q')
        s = local.inspect(self.clone)
        self.assertEqual(s.behind, 1)
        self.assertIn('↓1 outdated', [c.text for c in local.chips(s)])

    def test_diverged(self):
        self.push_from_other()
        commit(self.clone, 'c')
        s = local.inspect(self.clone)
        self.assertEqual((s.ahead, s.behind), (1, 1))
        self.assertIn('diverged', local.words(s))

    def test_detached(self):
        git(self.clone, 'checkout', '-q', '--detach')
        s = local.inspect(self.clone)
        self.assertIsNone(s.branch)
        self.assertTrue(local.chips(s)[0].text.startswith('⎇ detached '))

    def test_no_upstream_and_non_default_branch(self):
        git(self.clone, 'checkout', '-q', '-b', 'feat')
        s = local.inspect(self.clone)
        self.assertEqual((s.branch, s.upstream, s.ahead), ('feat', None, None))
        chips = local.chips(s)
        self.assertEqual(chips[0].css, 'warning')
        self.assertIn('no upstream', [c.text for c in chips])

    def test_does_not_touch_index_or_refs(self):
        index = os.path.join(self.clone, '.git', 'index')
        before = os.stat(index).st_mtime_ns
        local.inspect(self.clone)
        self.assertEqual(os.stat(index).st_mtime_ns, before)

    def test_repo_config_cannot_run_fsmonitor(self):
        marker = os.path.join(self.tmp.name, 'ran')
        git(self.clone, 'config', 'core.fsmonitor', f'touch {marker}; echo')
        local.inspect(self.clone)
        self.assertFalse(os.path.exists(marker))


class SearchChipsTest(unittest.TestCase):
    def test_search_words(self):
        s = RepoStatus(name='a', url='https://github.com/o/a')
        st = local.LocalState(branch='main', upstream='origin/main', ahead=0, behind=2, dirty=1)
        self.assertTrue(matches('behind dirty', 'github.com/o/a', 'a', s, st))
        self.assertFalse(matches('dirty', 'github.com/o/a', 'a', s, None))

    def test_old_fetch_chip(self):
        s = local.LocalState(branch='main', upstream='o/m', ahead=0, behind=0, fetched_at=0)
        old, recent = datetime(1970, 1, 11, tzinfo=timezone.utc), datetime(1970, 1, 3, tzinfo=timezone.utc)
        self.assertIn('fetched 10d ago', [c.text for c in local.chips(s, old)])
        shown = local.chips(s, recent)
        self.assertFalse(any('fetched' in c.text for c in shown))
        self.assertIn('Last fetch: 2d ago', shown[0].tooltip)

    def test_error_chip_and_unlinked(self):
        self.assertEqual(local.chips(None), [])
        self.assertEqual(local.chips(local.LocalState(error='missing'))[0].text, 'clone folder missing')


if __name__ == '__main__':
    unittest.main()
