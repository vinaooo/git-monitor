import unittest

from painel.chips import Chip, chips_for
from painel.status import RepoStatus


def status(ci=None, prs=None, total=None, **kw):  # kw may carry url=
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


class ChipLinkTest(unittest.TestCase):
    GH, GL = 'https://github.com/o/r', 'https://gitlab.com/g/p'

    def link(self, base, bucket):
        from painel.chips import pr_list_url
        return pr_list_url(base, bucket)

    def test_github_filters(self):
        q = lambda s: f'{self.GH}/pulls?q=is%3Apr+is%3Aopen+{s}'
        self.assertEqual(self.link(self.GH, 'draft'), q('draft%3Atrue'))
        self.assertEqual(self.link(self.GH, 'approved'), q('status%3Asuccess+-review%3Arequired'))
        self.assertEqual(self.link(self.GH, 'changes'), q('review%3Achanges_requested'))
        self.assertEqual(self.link(self.GH, 'waiting'), q('review%3Arequired+draft%3Afalse'))
        self.assertEqual(self.link(self.GH, 'failing'), q('status%3Afailure'))
        self.assertEqual(self.link(self.GH, 'conflict'), f'{self.GH}/pulls?q=is%3Apr+is%3Aopen')  # no qualifier exists
        self.assertEqual(self.link(self.GH, 'open'), f'{self.GH}/pulls?q=is%3Apr+is%3Aopen')

    def test_gitlab_filters(self):
        self.assertEqual(self.link(self.GL, 'draft'), f'{self.GL}/-/merge_requests?state=opened&draft=yes')
        self.assertEqual(self.link(self.GL, 'approved'), f'{self.GL}/-/merge_requests?state=opened&draft=no')
        self.assertEqual(self.link(self.GL, 'waiting'), f'{self.GL}/-/merge_requests?state=opened&draft=no')
        self.assertEqual(self.link(self.GL, 'conflict'), f'{self.GL}/-/merge_requests?state=opened')

    def test_no_url_no_link(self):
        self.assertEqual(self.link('', 'waiting'), '')

    def test_chips_carry_links_only_when_it_makes_sense(self):
        s = status(prs={'waiting': 8}, url='https://github.com/o/r')
        groups = dict(chips_for(s))
        self.assertTrue(groups['PRs'][0].url.startswith('https://github.com/o/r/pulls?q='))
        self.assertEqual(dict(chips_for(status(url='https://github.com/o/r')))['PRs'][0].url, '')  # "No open PRs"
        self.assertEqual(groups['CI'][0].url, '')
        anon = dict(chips_for(status(prs={'draft': 1}, total=7, pr_detail=False, url='https://github.com/o/r')))['PRs']
        self.assertEqual([bool(c.url) for c in anon], [True, True, False])  # "7 open", "1 draft", hint
