import unittest

from painel.chips import Chip, chips_for
from painel.status import RepoStatus


def status(ci=None, prs=None, total=None, **kw):
    ci_counts = {**dict(failure=0, running=0, cancelled=0, success=0), **(ci or {})}
    pr_counts = {**dict(changes=0, failing=0, conflict=0, waiting=0, approved=0, draft=0), **(prs or {})}
    return RepoStatus(name='x', ci_counts=ci_counts, pr_counts=pr_counts,
                      prs=sum(pr_counts.values()) if total is None else total, **kw)


def texts(groups, name):
    return [c.text for c in dict(groups)[name]]


class ChipsTest(unittest.TestCase):
    def test_ci_chips_worst_first_with_colors(self):
        groups = chips_for(status(ci={'failure': 1, 'running': 2, 'success': 3, 'cancelled': 1}))
        self.assertEqual(texts(groups, 'CI'), ['✗ 1 failing', '● 2 running', '⚠ 1 cancelled', '✓ 3 passing'])
        self.assertEqual([c.css for c in dict(groups)['CI']], ['error', 'accent', 'warning', 'success'])

    def test_no_ci(self):
        self.assertEqual(dict(chips_for(status()))['CI'], [Chip('No CI', 'dim-label', '')])

    def test_pr_chips(self):
        groups = chips_for(status(prs={'changes': 1, 'failing': 2, 'conflict': 1, 'waiting': 3, 'approved': 4, 'draft': 5}))
        self.assertEqual(texts(groups, 'PRs'), ['✎ 1 changes', '✗ 2 CI failing', '⚠ 1 conflicts',
                                                '◌ 3 waiting', '✓ 4 ready', '5 draft'])

    def test_no_prs(self):
        self.assertEqual(texts(chips_for(status()), 'PRs'), ['No open PRs'])

    def test_anonymous_github_is_honest(self):
        groups = chips_for(status(prs={'draft': 1}, total=7, pr_detail=False))
        self.assertEqual(texts(groups, 'PRs'), ['7 open', '1 draft', 'no review detail · add a token'])

    def test_tooltips_come_from_details(self):
        s = status(ci={'failure': 1}, prs={'changes': 1}, details={'ci-failure': ['build'], 'changes': ['#2 fix']})
        groups = dict(chips_for(s))
        self.assertEqual(groups['CI'][0].tooltip, 'build')
        self.assertEqual(groups['PRs'][0].tooltip, '#2 fix')

    def test_error_status_has_no_chips(self):
        self.assertEqual(chips_for(RepoStatus(name='x', error='Not found')), [])
