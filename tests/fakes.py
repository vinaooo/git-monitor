from painel.http import HttpClient


class FakeHttp(HttpClient):
    """Routes: {url substring: (json body, headers)}, first match wins; `error` raises instead.
    GET and POST share routes; POST bodies are recorded in `bodies`."""

    def __init__(self, routes=None, error=None):
        self.routes, self.error, self.urls, self.sent, self.bodies = routes or {}, error, [], [], []

    def _respond(self, url, headers):
        self.urls.append(url)
        self.sent.append(headers or {})
        if self.error:
            raise self.error
        for key, resp in self.routes.items():
            if key in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f'unrouted {url}')

    def get(self, url, headers=None):
        return self._respond(url, headers)

    def post(self, url, body, headers=None):
        self.bodies.append(body)
        return self._respond(url, headers)
