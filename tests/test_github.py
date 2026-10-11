import unittest

from painel.github import GitHubProvider
from tests.fakes import FakeHttp

REPO = {'full_name': 'O/r', 'html_url': 'https://github.com/O/r', 'open_issues_count': 10, 'default_branch': 'main'}


def wrun(wf, status, conclusion=None):
    return {'workflow_id': wf, 'name': f'wf{wf}', 'status': status, 'conclusion': conclusion}


def routes(runs=(), running=0, pulls=(), graphql=None):
    r = {'/repos/o/r/pulls': (list(pulls), {}),
         'status=in_progress': ({'total_count': running}, {}),
         'branch=main': ({'workflow_runs': list(runs)}, {}),
         '/repos/o/r': (REPO, {})}
    if graphql is not None:
        r = {'/graphql': ({'data': {'repository': {'pullRequests': graphql}}}, {}), **r}
    return r


def node(n, **kw):
    base = {'number': n, 'title': f'pr{n}', 'isDraft': False, 'reviewDecision': None, 'mergeable': 'MERGEABLE',
            'commits': {'nodes': [{'commit': {'statusCheckRollup': {'state': 'SUCCESS'}}}]}}
    base.update(kw)
    return base


class GitHubCiTest(unittest.TestCase):
    def fetch(self, **kw):
        return GitHubProvider(FakeHttp(routes(**kw))).fetch('o/r', None)

    def test_basic_fields_and_branch_filtered_runs(self):
        http = FakeHttp(routes())
        s = GitHubProvider(http).fetch('o/r', None)
        self.assertEqual((s.name, s.url, s.ci), ('O/r', 'https://github.com/O/r', 'none'))
        self.assertTrue(any('branch=main' in u for u in http.urls))

    def test_multiple_workflows_summarized(self):
        s = self.fetch(runs=[wrun(1, 'completed', 'failure'), wrun(1, 'completed', 'success'),
                             wrun(2, 'in_progress'), wrun(3, 'completed', 'success'),
                             wrun(4, 'completed', 'cancelled')], running=2)
        self.assertEqual(s.ci_counts, {'failure': 1, 'running': 2, 'cancelled': 1, 'success': 1})
        self.assertEqual(s.ci, 'failure')
        self.assertEqual(s.details['ci-failure'], ['wf1'])

    def test_running_elsewhere_counts(self):
        s = self.fetch(runs=[wrun(1, 'completed', 'success')], running=3)
        self.assertEqual((s.ci_counts['running'], s.ci), (3, 'running'))

    def test_timed_out_is_failure_skipped_is_ignored(self):
        self.assertEqual(self.fetch(runs=[wrun(1, 'completed', 'timed_out')]).ci, 'failure')
        self.assertEqual(self.fetch(runs=[wrun(1, 'completed', 'skipped')]).ci, 'none')


class GitHubPrTest(unittest.TestCase):
    def test_anonymous_uses_rest_and_hides_review_states(self):
        http = FakeHttp(routes(pulls=[{'number': 1, 'title': 'a', 'draft': True},
                                      {'number': 2, 'title': 'b', 'draft': False}]))
        s = GitHubProvider(http).fetch('o/r', None)
        self.assertEqual((s.prs, s.issues, s.pr_detail), (2, 8, False))
        self.assertEqual(s.pr_counts['draft'], 1)
        self.assertEqual(s.pr_counts['approved'] + s.pr_counts['waiting'], 0)
        self.assertFalse(any('/graphql' in u for u in http.urls))

    def test_token_uses_graphql_for_review_states(self):
        gql = {'totalCount': 3, 'nodes': [node(1, reviewDecision='APPROVED'),
                                          node(2, reviewDecision='CHANGES_REQUESTED'),
                                          node(3, isDraft=True)]}
        http = FakeHttp(routes(graphql=gql))
        s = GitHubProvider(http).fetch('o/r', 'tok')
        self.assertEqual((s.prs, s.issues, s.pr_detail), (3, 7, True))
        self.assertEqual((s.pr_counts['approved'], s.pr_counts['changes'], s.pr_counts['draft']), (1, 1, 1))
        self.assertEqual(s.details['changes'], ['#2 pr2'])
        self.assertTrue(all(h['Authorization'] == 'Bearer tok' for h in http.sent))
        self.assertEqual(http.bodies[0]['variables'], {'owner': 'o', 'name': 'r'})
