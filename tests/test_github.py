import unittest

from painel.github import GitHubProvider
from painel.http import HttpError
from painel.status import RepoInfo
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


def repo(name, fork=False, archived=False, private=False):
    return {'full_name': name, 'fork': fork, 'archived': archived, 'private': private}


def link(url):
    return {'Link': f'<{url}>; rel="next", <{url}>; rel="last"'}


class GitHubListTest(unittest.TestCase):
    def list(self, routes, account='o', token=None):
        http = FakeHttp(routes)
        return GitHubProvider(http).list_repos(account, token), http

    def test_anonymous_lists_public_repos_of_the_account(self):
        (infos, truncated), http = self.list({'/users/o/repos': ([repo('o/a'), repo('o/b', fork=True, archived=True)], {})})
        self.assertEqual(infos, [RepoInfo('o/a', False, False, False), RepoInfo('o/b', True, True, False)])
        self.assertFalse(truncated)
        self.assertNotIn('Authorization', http.sent[0])

    def test_follows_pagination(self):
        page2 = 'https://api.github.com/users/o/repos?per_page=100&page=2'
        (infos, truncated), http = self.list({'page=2': ([repo('o/b')], {}),
                                              '/users/o/repos': ([repo('o/a')], link(page2))})
        self.assertEqual([i.path for i in infos], ['o/a', 'o/b'])
        self.assertFalse(truncated)

    def test_page_cap_marks_truncated(self):
        endless = 'https://api.github.com/users/o/repos?per_page=100&page=2'
        (infos, truncated), http = self.list({'/users/o/repos': ([repo('o/a')], link(endless))})
        self.assertTrue(truncated)
        self.assertEqual(len(http.urls), 10)

    def test_own_account_with_token_includes_private(self):
        (infos, _), http = self.list({'/user/repos': ([repo('O/a', private=True)], {}), '/user': ({'login': 'O'}, {})},
                                     account='o', token='tok')
        self.assertTrue(infos[0].private)
        self.assertTrue(any('/user/repos?affiliation=owner' in u for u in http.urls))
        self.assertTrue(all(h['Authorization'] == 'Bearer tok' for h in http.sent))

    def test_other_account_with_token_is_tried_as_org_then_user(self):
        (infos, _), http = self.list({'/orgs/acme/repos': ([repo('acme/a', private=True)], {}), '/user': ({'login': 'me'}, {})},
                                     account='acme', token='tok')
        self.assertEqual(infos[0].path, 'acme/a')
        (infos, _), http = self.list({'/orgs/someone/repos': HttpError(404), '/users/someone/repos': ([repo('someone/x')], {}),
                                      '/user': ({'login': 'me'}, {})}, account='someone', token='tok')
        self.assertEqual(infos[0].path, 'someone/x')

    def test_other_http_errors_propagate(self):
        with self.assertRaises(HttpError):
            self.list({'/orgs/acme/repos': HttpError(403), '/user': ({'login': 'me'}, {})}, account='acme', token='tok')


def gql_repo(name='O/r', issues=7, prs=(), branch='main'):
    return {'nameWithOwner': name, 'url': f'https://github.com/{name}', 'issues': {'totalCount': issues},
            'defaultBranchRef': {'name': branch} if branch else None,
            'pullRequests': {'totalCount': len(prs), 'nodes': list(prs)}}


class GitHubBatchTest(unittest.TestCase):
    def heads(self, data, paths=('o/r', 'o/s'), token='tok'):
        http = FakeHttp({'/graphql': ({'data': data}, {})})
        return GitHubProvider(http).heads(list(paths), token), http

    def test_one_query_for_all_repos_with_variables_not_interpolation(self):
        heads, http = self.heads({'r0': gql_repo(), 'r1': gql_repo('O/s')})
        self.assertEqual(len(http.bodies), 1)
        self.assertEqual(http.bodies[0]['variables'], {'o0': 'o', 'n0': 'r', 'o1': 'o', 'n1': 's'})
        self.assertIn('r1: repository(owner: $o1, name: $n1)', http.bodies[0]['query'])
        self.assertEqual(http.sent[0]['Authorization'], 'Bearer tok')
        self.assertEqual((heads['o/r'].name, heads['o/s'].name), ('O/r', 'O/s'))

    def test_head_carries_issues_prs_and_branch(self):
        prs = [node(1, reviewDecision='APPROVED'), node(2, isDraft=True)]
        heads, _ = self.heads({'r0': gql_repo(issues=4, prs=prs), 'r1': None})
        h = heads['o/r']
        self.assertEqual((h.issues, h.prs, h.branch, h.detail), (4, 2, 'main', True))
        self.assertEqual((h.pr_counts['approved'], h.pr_counts['draft']), (1, 1))

    def test_missing_or_empty_repos_are_none_so_the_caller_falls_back(self):
        heads, _ = self.heads({'r0': None, 'r1': gql_repo(branch=None)})
        self.assertEqual(heads, {'o/r': None, 'o/s': None})

    def test_fetch_with_a_head_skips_the_repo_and_pr_calls(self):
        heads, _ = self.heads({'r0': gql_repo(issues=4, prs=[node(1)]), 'r1': None})
        http = FakeHttp(routes(runs=[wrun(1, 'completed', 'failure')], running=1))
        s = GitHubProvider(http).fetch('o/r', 'tok', heads['o/r'])
        self.assertEqual((s.name, s.url, s.issues, s.prs, s.ci), ('O/r', 'https://github.com/O/r', 4, 1, 'failure'))
        self.assertTrue(s.pr_detail)
        self.assertEqual(len(http.urls), 2)
        self.assertTrue(all('/actions/runs' in u for u in http.urls))
        self.assertTrue(any('branch=main' in u for u in http.urls))

    def test_batch_status_equals_the_per_repo_status(self):
        gql = {'totalCount': 1, 'nodes': [node(1, reviewDecision='APPROVED')]}
        alone = GitHubProvider(FakeHttp(routes(graphql=gql))).fetch('o/r', 'tok')
        heads, _ = self.heads({'r0': gql_repo(issues=10 - 1, prs=gql['nodes']), 'r1': None})
        batched = GitHubProvider(FakeHttp(routes())).fetch('o/r', 'tok', heads['o/r'])
        self.assertEqual(alone, batched)


ALL = frozenset({'security', 'reviews', 'release', 'push'})
THREADS = {'nodes': [{'isResolved': False}, {'isResolved': True}, {'isResolved': False}]}


def signal_repo(**kw):
    r = gql_repo(prs=[node(1, reviewThreads=THREADS), node(2, reviewThreads={'nodes': []})])
    r.update(vulnerabilityAlerts={'totalCount': 3}, pushedAt='2026-10-01T00:00:00Z',
             latestRelease={'tagName': 'v1.2', 'publishedAt': '2026-09-01T00:00:00Z'})
    r.update(kw)
    return r


class GitHubSignalsTest(unittest.TestCase):
    def heads(self, signals, repo=None, token='tok'):
        http = FakeHttp({'/graphql': ({'data': {'r0': repo or signal_repo()}}, {})})
        return GitHubProvider(http, signals).heads(['o/r'], token), http

    def test_disabled_signals_add_nothing_to_the_query(self):
        _, http = self.heads(frozenset())
        q = http.bodies[0]['query']
        for field in ('vulnerabilityAlerts', 'reviewThreads', 'latestRelease', 'pushedAt'):
            self.assertNotIn(field, q)

    def test_each_enabled_signal_adds_its_field(self):
        _, http = self.heads(ALL)
        q = http.bodies[0]['query']
        for field in ('vulnerabilityAlerts', 'reviewThreads', 'latestRelease', 'pushedAt'):
            self.assertIn(field, q)

    def test_head_parses_signals(self):
        heads, _ = self.heads(ALL)
        x = heads['o/r'].extra
        self.assertEqual((x['dependabot'], x['unresolved'], x['release'], x['released_at'], x['pushed_at']),
                         (3, 2, 'v1.2', '2026-09-01T00:00:00Z', '2026-10-01T00:00:00Z'))
        self.assertEqual(heads['o/r'].pr_details['unresolved'], ['#1 pr1: 2'])

    def test_no_access_or_no_release_stays_unknown(self):
        heads, _ = self.heads(ALL, signal_repo(vulnerabilityAlerts=None, latestRelease=None))
        x = heads['o/r'].extra
        self.assertNotIn('dependabot', x)
        self.assertNotIn('release', x)

    def fetch(self, signals, token='tok', scanning=None, off=None, runs=True):
        http = FakeHttp({'code-scanning': scanning if scanning is not None else ([{}, {}], {}), **routes()})
        p = GitHubProvider(http, signals, off if off is not None else set())
        heads, _ = self.heads(signals)
        return p.fetch('o/r', token, heads['o/r']), http, p

    def test_fetch_merges_head_signals_and_code_scanning(self):
        s, _, _ = self.fetch(ALL)
        self.assertEqual((s.dependabot, s.code_scanning, s.unresolved, s.release, s.pushed_at),
                         (3, 2, 2, 'v1.2', '2026-10-01T00:00:00Z'))

    def test_code_scanning_not_requested_when_disabled_or_anonymous(self):
        _, http, _ = self.fetch(frozenset({'push'}))
        self.assertFalse(any('code-scanning' in u for u in http.urls))
        http = FakeHttp({'/releases/latest': HttpError(404), **routes()})
        s = GitHubProvider(http, ALL).fetch('o/r', None)
        self.assertFalse(any(k in u for u in http.urls for k in ('code-scanning', '/graphql')))
        self.assertIsNone(s.code_scanning)

    def test_code_scanning_denied_is_silent_and_never_retried(self):
        off = set()
        s, http, p = self.fetch(ALL, scanning=HttpError(403), off=off)
        self.assertIsNone(s.error)
        self.assertIsNone(s.code_scanning)
        heads, _ = self.heads(ALL)
        before = sum('code-scanning' in u for u in http.urls)
        p.fetch('o/r', 'tok', heads['o/r'])
        self.assertEqual(before, sum('code-scanning' in u for u in http.urls))

    def test_code_scanning_page_cap_is_kept_as_100(self):
        s, _, _ = self.fetch(ALL, scanning=([{}] * 100, {}))
        self.assertEqual(s.code_scanning, 100)

    def test_rest_path_gets_pushed_at_and_release(self):
        http = FakeHttp({'/releases/latest': ({'tag_name': 'v9', 'published_at': '2026-01-01T00:00:00Z'}, {}),
                         **routes()})
        http.routes['/repos/o/r'] = (dict(REPO, pushed_at='2026-02-02T00:00:00Z'), {})
        s = GitHubProvider(http, frozenset({'release', 'push'})).fetch('o/r', None)
        self.assertEqual((s.release, s.released_at, s.pushed_at), ('v9', '2026-01-01T00:00:00Z', '2026-02-02T00:00:00Z'))

    def test_rest_path_without_a_release_is_not_an_error(self):
        http = FakeHttp({'/releases/latest': HttpError(404), **routes()})
        s = GitHubProvider(http, frozenset({'release'})).fetch('o/r', None)
        self.assertIsNone(s.release)
