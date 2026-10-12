import unittest

from painel.forgejo import LIMIT, MAX_PAGES, ForgejoProvider
from painel.http import HttpError
from painel.status import RepoInfo
from tests.fakes import FakeHttp

REPO = {'full_name': 'o/r', 'html_url': 'https://codeberg.org/o/r', 'default_branch': 'main',
        'open_issues_count': 7, 'open_pr_counter': 3}


def pr(n, draft=False, mergeable=True, title=None):
    return {'number': n, 'title': title or f'pr{n}', 'draft': draft, 'mergeable': mergeable}


def st(context, status):
    return {'context': context, 'status': status}


def routes(prs=(), statuses=(), total=None, repo=REPO):
    return {'/pulls': (list(prs), {'X-Total-Count': str(len(prs) if total is None else total)}),
            '/commits/main/status': ({'state': 'x', 'statuses': list(statuses)}, {}),
            '/repos/o/r': (repo, {})}


def repo_item(name, fork=False, archived=False, private=False, owner='acct'):
    return {'full_name': f'{owner}/{name}', 'fork': fork, 'archived': archived, 'private': private, 'owner': {'login': owner}}


class ForgejoTest(unittest.TestCase):
    def fetch(self, token=None, **kw):
        http = FakeHttp(routes(**kw))
        return ForgejoProvider('codeberg.org', http).fetch('o/r', token), http

    def test_basic_fields(self):
        s, http = self.fetch()
        self.assertEqual((s.name, s.url, s.issues, s.prs, s.ci), ('o/r', 'https://codeberg.org/o/r', 7, 0, 'none'))
        self.assertTrue(http.urls[0].startswith('https://codeberg.org/api/v1/repos/o/r'))

    def test_pr_total_comes_from_header(self):
        self.assertEqual(self.fetch(prs=[pr(1)], total=120)[0].prs, 120)

    def test_pr_total_falls_back_to_counter(self):
        s, _ = self.fetch(prs=[pr(1)], total='')
        self.assertEqual(s.prs, 3)

    def test_pr_buckets(self):
        s, _ = self.fetch(prs=[pr(1), pr(2, mergeable=False), pr(3, draft=True, mergeable=False),
                               pr(4, title='WIP: later')])
        self.assertEqual(s.pr_counts, {'changes': 0, 'failing': 0, 'conflict': 1, 'waiting': 1, 'approved': 0, 'draft': 2})
        self.assertEqual(s.details['conflict'], ['#2 pr2'])

    def test_ci_from_commit_statuses(self):
        s, _ = self.fetch(statuses=[st('/ build (push)', 'success'), st('/ lint (push)', 'failure'),
                                    st('/ e2e (push)', 'pending'), st('/ x (push)', 'skipped'),
                                    st('ci/other', 'error')])
        self.assertEqual(s.ci_counts, {'failure': 2, 'running': 1, 'cancelled': 0, 'success': 1})
        self.assertEqual(s.ci, 'failure')
        self.assertEqual(s.details['ci-success'], ['build (push)'])

    def test_only_skipped_is_no_ci(self):
        self.assertEqual(self.fetch(statuses=[st('a', 'skipped')])[0].ci, 'none')

    def test_pending_is_running(self):
        self.assertEqual(self.fetch(statuses=[st('a', 'pending')])[0].ci, 'running')

    def test_token_header(self):
        _, http = self.fetch('tok')
        self.assertTrue(all(h == {'Authorization': 'token tok'} for h in http.sent))
        self.assertTrue(all(h == {} for h in self.fetch()[1].sent))

    def test_http_error_propagates(self):
        with self.assertRaises(HttpError):
            ForgejoProvider('codeberg.org', FakeHttp(error=HttpError(404))).fetch('o/r', None)


class ListReposTest(unittest.TestCase):
    def test_org(self):
        http = FakeHttp({'/orgs/acct/repos': ([repo_item('a'), repo_item('b', fork=True, archived=True, private=True)], {}),
                         '/orgs/acct': ({}, {})})
        infos, truncated = ForgejoProvider('codeberg.org', http).list_repos('acct', None)
        self.assertEqual(infos, [RepoInfo('acct/a', False, False, False), RepoInfo('acct/b', True, True, True)])
        self.assertFalse(truncated)

    def test_user_when_not_an_org(self):
        http = FakeHttp({'/orgs/acct/repos': AssertionError('no'), '/orgs/acct': HttpError(404),
                         '/users/acct/repos': ([repo_item('a')], {})})
        self.assertEqual(ForgejoProvider('codeberg.org', http).list_repos('acct', None)[0], [RepoInfo('acct/a', False, False, False)])

    def test_other_error_not_swallowed(self):
        http = FakeHttp({'/orgs/acct': HttpError(500)})
        with self.assertRaises(HttpError):
            ForgejoProvider('codeberg.org', http).list_repos('acct', None)

    def test_own_account_with_token_lists_private_and_skips_others(self):
        http = FakeHttp({'/user/repos': ([repo_item('mine', private=True), repo_item('shared', owner='other')], {}),
                         '/api/v1/user': ({'login': 'Acct'}, {})})
        infos, _ = ForgejoProvider('codeberg.org', http).list_repos('acct', 'tok')
        self.assertEqual(infos, [RepoInfo('acct/mine', False, False, True)])
        self.assertEqual(http.sent[0], {'Authorization': 'token tok'})

    def test_pagination_and_cap(self):
        full = [repo_item(str(i)) for i in range(LIMIT)]
        http = FakeHttp({'page=1': (full, {}), 'page=2': (full[:3], {}), '/orgs/acct/repos': AssertionError('x'), '/orgs/acct': ({}, {})})
        infos, truncated = ForgejoProvider('codeberg.org', http).list_repos('acct', None)
        self.assertEqual((len(infos), truncated), (LIMIT + 3, False))
        http = FakeHttp({'/orgs/acct/repos': (full, {}), '/orgs/acct': ({}, {})})
        infos, truncated = ForgejoProvider('codeberg.org', http).list_repos('acct', None)
        self.assertEqual((len(infos), truncated), (LIMIT * MAX_PAGES, True))


if __name__ == '__main__':
    unittest.main()
