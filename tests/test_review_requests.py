import unittest

from painel.http import HttpError
from painel.review_requests import ReviewRequests
from tests.fakes import FakeHttp

GH = {'/search/issues': ({'items': [{'repository_url': 'https://api.github.com/repos/O/R'},
                                    {'repository_url': 'https://api.github.com/repos/a/b'}]}, {})}
GL = {'/api/v4/user': ({'id': 7}, {}),
      '/merge_requests': ([{'references': {'full': 'g/sub/p!12'}}, {'references': {'full': 'g/q!3'}}], {})}


class ReviewRequestsTest(unittest.TestCase):
    def test_github_search_lowercased_paths(self):
        http = FakeHttp(GH)
        self.assertEqual(ReviewRequests(http).paths('github.com', 'tok'), {'o/r', 'a/b'})
        self.assertIn('review-requested:@me', http.urls[0])
        self.assertEqual(http.sent[0]['Authorization'], 'Bearer tok')

    def test_no_token_no_request(self):
        http = FakeHttp(GH)
        self.assertEqual(ReviewRequests(http).paths('github.com', None), set())
        self.assertEqual(http.urls, [])

    def test_gitlab_user_fetched_once(self):
        http = FakeHttp(GL)
        rr = ReviewRequests(http)
        self.assertEqual(rr.paths('gitlab.com', 'tok'), {'g/sub/p', 'g/q'})
        rr.paths('gitlab.com', 'tok')
        self.assertEqual(sum('/api/v4/user' in u for u in http.urls), 1)
        self.assertTrue(all('reviewer_id=7' in u for u in http.urls if '/merge_requests' in u))
        self.assertEqual(http.sent[0]['PRIVATE-TOKEN'], 'tok')

    def test_gitlab_new_token_refetches_user(self):
        http = FakeHttp(GL)
        rr = ReviewRequests(http)
        rr.paths('gitlab.com', 'a')
        rr.paths('gitlab.com', 'b')
        self.assertEqual(sum('/api/v4/user' in u for u in http.urls), 2)

    def test_other_hosts_empty(self):
        self.assertEqual(ReviewRequests(FakeHttp()).paths('codeberg.org', 'tok'), set())

    def test_errors_propagate(self):
        with self.assertRaises(HttpError):
            ReviewRequests(FakeHttp(error=HttpError(401))).paths('github.com', 'tok')


if __name__ == '__main__':
    unittest.main()
