import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from painel.http import UrllibClient


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
