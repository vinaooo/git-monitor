import unittest

from painel.gitlab import GitLabProvider
from painel.status import RepoInfo
from tests.fakes import FakeHttp

PROJECT = {'name_with_namespace': 'G / Sub / P', 'web_url': 'https://gitlab.com/g/sub/p', 'default_branch': 'main'}


def pipe(pid, status, source='push'):
    return {'id': pid, 'status': status, 'source': source}


def mr(iid, status, draft=False):
    return {'iid': iid, 'title': f'mr{iid}', 'draft': draft, 'detailed_merge_status': status}


def routes(pipes=(), running=0, mrs=(), total=None):
    return {'/merge_requests': (list(mrs), {'X-Total': str(len(mrs) if total is None else total)}),
            '/issues_statistics': ({'statistics': {'counts': {'opened': 9}}}, {}),
            'status=running': ([{}] * running, {}),
            'ref=main': (list(pipes), {}),
            '/projects/g%2Fsub%2Fp': (PROJECT, {})}


class GitLabTest(unittest.TestCase):
    def fetch(self, token=None, **kw):
        http = FakeHttp(routes(**kw))
        return GitLabProvider('gitlab.com', http).fetch('g/sub/p', token), http

    def test_basic_fields(self):
        s, http = self.fetch()
        self.assertEqual((s.name, s.url, s.issues, s.prs, s.ci), ('G/Sub/P', 'https://gitlab.com/g/sub/p', 9, 0, 'none'))
        self.assertTrue(http.urls[0].startswith('https://gitlab.com/api/v4/projects/g%2Fsub%2Fp'))

    def test_mr_states_from_detailed_merge_status(self):
        s, _ = self.fetch(mrs=[mr(1, 'mergeable'), mr(2, 'requested_changes'), mr(3, 'conflict'),
                               mr(4, 'ci_must_pass'), mr(5, 'not_approved'), mr(6, 'conflict', draft=True)])
        self.assertEqual(s.prs, 6)
        self.assertEqual(s.pr_counts, {'approved': 1, 'changes': 1, 'conflict': 1, 'failing': 1, 'waiting': 1, 'draft': 1})
        self.assertEqual(s.details['changes'], ['!2 mr2'])
        self.assertTrue(s.pr_detail)

    def test_total_comes_from_header_not_page_size(self):
        self.assertEqual(self.fetch(mrs=[mr(1, 'mergeable')], total=120)[0].prs, 120)

    def test_missing_total_header_is_zero(self):
        s, _ = self.fetch(mrs=[], total='')
        self.assertEqual(s.prs, 0)

    def test_pipelines_aggregate_latest_per_source(self):
        s, _ = self.fetch(pipes=[pipe(5, 'failed'), pipe(4, 'success'),            # push: latest failed
                                 pipe(3, 'running', 'schedule'), pipe(2, 'canceled', 'web')], running=2)
        self.assertEqual(s.ci_counts, {'failure': 1, 'running': 2, 'cancelled': 1, 'success': 0})
        self.assertEqual(s.ci, 'failure')

    def test_pending_and_created_count_as_running_skipped_ignored(self):
        self.assertEqual(self.fetch(pipes=[pipe(1, 'pending')])[0].ci, 'running')
        self.assertEqual(self.fetch(pipes=[pipe(1, 'skipped')])[0].ci, 'none')

    def test_token_header(self):
        _, http = self.fetch(token='tok')
        self.assertTrue(all(h['PRIVATE-TOKEN'] == 'tok' for h in http.sent))


def proj(path, forked=False, archived=False, visibility='public'):
    p = {'path_with_namespace': path, 'archived': archived, 'visibility': visibility}
    if forked:
        p['forked_from_project'] = {'id': 1}
    return p


class GitLabListTest(unittest.TestCase):
    def list(self, routes, account='me', token=None):
        http = FakeHttp(routes)
        return GitLabProvider('gitlab.com', http).list_repos(account, token), http

    def test_user_projects_with_kinds(self):
        (infos, truncated), http = self.list({'/users/7/projects': ([proj('me/a'), proj('me/b', forked=True, archived=True),
                                                                      proj('me/c', visibility='private')], {}),
                                              '/users?username=me': ([{'id': 7}], {})})
        self.assertEqual(infos, [RepoInfo('me/a', False, False, False), RepoInfo('me/b', True, True, False),
                                 RepoInfo('me/c', False, False, True)])
        self.assertFalse(truncated)

    def test_unknown_user_falls_back_to_group_with_subgroups(self):
        (infos, _), http = self.list({'/groups/g%2Fsub/projects': ([proj('g/sub/p')], {}), '/users?username': ([], {})},
                                     account='g/sub')
        self.assertEqual(infos[0].path, 'g/sub/p')
        self.assertTrue(any('include_subgroups=true' in u for u in http.urls))

    def test_follows_x_next_page_and_sends_token(self):
        (infos, truncated), http = self.list({'page=2': ([proj('me/b')], {'X-Next-Page': ''}),
                                              '/users/7/projects': ([proj('me/a')], {'X-Next-Page': '2'}),
                                              '/users?username=me': ([{'id': 7}], {})}, token='tok')
        self.assertEqual([i.path for i in infos], ['me/a', 'me/b'])
        self.assertFalse(truncated)
        self.assertTrue(all(h['PRIVATE-TOKEN'] == 'tok' for h in http.sent))

    def test_page_cap_marks_truncated(self):
        (infos, truncated), http = self.list({'/users/7/projects': ([proj('me/a')], {'X-Next-Page': '2'}),
                                              '/users?username=me': ([{'id': 7}], {})})
        self.assertTrue(truncated)
