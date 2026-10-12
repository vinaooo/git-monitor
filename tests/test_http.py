import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from painel.http import CachingClient, HttpError, RateState, UrllibClient
from tests.fakes import FakeHttp


def serve(handler):
    srv = HTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class RedirectTest(unittest.TestCase):
    def test_cross_host_redirect_drops_credentials(self):
        seen = {}

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.update(self.headers)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{}')

            def log_message(self, *a):
                pass

        target = serve(Target)

        class Origin(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', f'http://127.0.0.1:{target.server_port}/x')
                self.end_headers()

            def log_message(self, *a):
                pass

        origin = serve(Origin)
        self.addCleanup(lambda: (origin.shutdown(), target.shutdown()))
        UrllibClient().get(f'http://127.0.0.1:{origin.server_port}/',
                           {'Authorization': 'Bearer s3cret', 'PRIVATE-TOKEN': 's3cret', 'Accept': 'x'})
        names = {k.lower() for k in seen}
        self.assertNotIn('authorization', names)
        self.assertNotIn('private-token', names)
        self.assertIn('accept', names)


class ConditionalServerTest(unittest.TestCase):
    """Real round trip: urllib raises HTTPError(304); the caching client must hide it."""

    def test_second_get_is_a_304_served_from_cache(self):
        seen = []

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get('If-None-Match'))
                if self.headers.get('If-None-Match') == '"v1"':
                    self.send_response(304)
                    self.send_header('X-RateLimit-Remaining', '4999')
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header('ETag', '"v1"')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"n": 1}')

            def log_message(self, *a):
                pass

        srv = serve(H)
        self.addCleanup(srv.shutdown)
        client = CachingClient(UrllibClient())
        url = f'http://127.0.0.1:{srv.server_port}/'
        self.assertEqual(client.get(url)[0], {'n': 1})
        self.assertEqual(client.get(url)[0], {'n': 1})
        self.assertEqual(seen, [None, '"v1"'])

    def test_429_carries_retry_after_headers(self):
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(429)
                self.send_header('Retry-After', '42')
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = serve(H)
        self.addCleanup(srv.shutdown)
        with self.assertRaises(HttpError) as cm:
            UrllibClient().get(f'http://127.0.0.1:{srv.server_port}/')
        self.assertEqual(cm.exception.headers['Retry-After'], '42')


URL, AUTH = 'https://api.github.com/repos/o/r', {'Authorization': 'Bearer a'}


class CachingClientTest(unittest.TestCase):
    def setUp(self):
        self.http = FakeHttp({'/repos': ({'v': 1}, {'ETag': '"e1"', 'Last-Modified': 'Mon'})})
        self.client = CachingClient(self.http, min_samples=2)

    def test_validators_are_sent_and_the_304_body_comes_from_cache(self):
        self.client.get(URL, AUTH)
        self.http.routes['/repos'] = HttpError(304)
        body, hdr = self.client.get(URL, AUTH)
        self.assertEqual((body, hdr['ETag']), ({'v': 1}, '"e1"'))
        self.assertEqual((self.http.sent[1]['If-None-Match'], self.http.sent[1]['If-Modified-Since']), ('"e1"', 'Mon'))
        self.assertNotIn('If-None-Match', self.http.sent[0])
        self.assertEqual(AUTH, {'Authorization': 'Bearer a'})  # caller's dict untouched

    def test_changed_resource_replaces_the_cache(self):
        self.client.get(URL, AUTH)
        self.http.routes['/repos'] = ({'v': 2}, {'ETag': '"e2"'})
        self.assertEqual(self.client.get(URL, AUTH)[0], {'v': 2})
        self.http.routes['/repos'] = HttpError(304)
        self.assertEqual(self.client.get(URL, AUTH)[0], {'v': 2})

    def test_another_token_never_reuses_the_cache(self):
        self.client.get(URL, AUTH)
        self.client.get(URL, {'Authorization': 'Bearer b'})
        self.assertNotIn('If-None-Match', self.http.sent[1])
        self.client.get(URL)
        self.assertNotIn('If-None-Match', self.http.sent[2])

    def test_without_validators_nothing_is_cached(self):
        self.http.routes['/repos'] = ({'v': 1}, {})
        self.client.get(URL, AUTH)
        self.client.get(URL, AUTH)
        self.assertNotIn('If-None-Match', self.http.sent[1])

    def test_other_errors_pass_through(self):
        self.http.routes['/repos'] = HttpError(404)
        with self.assertRaises(HttpError):
            self.client.get(URL, AUTH)

    def test_hit_ratio_needs_enough_samples(self):
        self.assertEqual(self.client.hit_ratio(), 0.0)
        self.client.get(URL, AUTH)
        self.assertEqual(self.client.hit_ratio(), 0.0)  # 1 sample < min_samples
        self.http.routes['/repos'] = HttpError(304)
        self.client.get(URL, AUTH)
        self.assertEqual(self.client.hit_ratio(), 0.5)

    def test_cache_is_bounded(self):
        client = CachingClient(self.http, size=2)
        for i in range(3):
            client.get(f'{URL}{i}', AUTH)
        self.http.routes['/repos'] = HttpError(304)
        with self.assertRaises(HttpError):
            client.get(f'{URL}0', AUTH)  # evicted: nothing to serve the 304 from

    def test_post_passes_through_and_feeds_rate_state(self):
        http = FakeHttp({'/graphql': ({'data': {}}, {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '1100'})})
        client = CachingClient(http, RateState(clock=lambda: 1000))
        self.assertEqual(client.post('https://api.github.com/graphql', {'q': 1}, AUTH)[0], {'data': {}})
        self.assertEqual(client.state.wait('api.github.com'), 100)


class RateStateTest(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.state = RateState(clock=lambda: self.now)

    def test_retry_after_blocks_the_host_until_it_passes(self):
        self.state.note('https://a.test/x', {'Retry-After': '30'})
        self.assertEqual(self.state.wait('a.test'), 30)
        self.assertEqual(self.state.wait('b.test'), 0)
        self.now = 1031
        self.assertEqual(self.state.wait('a.test'), 0)

    def test_exhausted_quota_waits_for_the_reset(self):
        self.state.note('https://a.test/x', {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '1500'})
        self.assertEqual(self.state.wait('a.test'), 500)

    def test_gitlab_header_names(self):
        self.state.note('https://a.test/x', {'RateLimit-Remaining': '0', 'RateLimit-Reset': '1060'})
        self.assertEqual(self.state.wait('a.test'), 60)

    def test_poll_interval_is_a_floor(self):
        self.state.note('https://a.test/x', {'X-Poll-Interval': '60'})
        self.assertEqual(self.state.wait('a.test'), 60)

    def test_healthy_response_clears_the_wait(self):
        self.state.note('https://a.test/x', {'Retry-After': '30'})
        self.state.note('https://a.test/x', {'X-RateLimit-Remaining': '4000'})
        self.assertEqual(self.state.wait('a.test'), 0)

    def test_ignores_garbage_and_missing_headers(self):
        self.state.note('https://a.test/x', {'Retry-After': 'soon'})
        self.state.note('https://a.test/x', None)
        self.assertEqual(self.state.wait('a.test'), 0)

    def test_error_response_headers_count_too(self):
        self.state.note('https://a.test/x', HttpError(403, {'Retry-After': '9'}).headers)
        self.assertEqual(self.state.wait('a.test'), 9)
