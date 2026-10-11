from painel.http import HttpClient


class FakeHttp(HttpClient):
    """Routes: {url substring: (json body, headers)}; `error` raises instead."""

    def __init__(self, routes=None, error=None):
        self.routes, self.error, self.urls, self.sent = routes or {}, error, [], []

    def get(self, url, headers=None):
        self.urls.append(url)
        self.sent.append(headers or {})
        if self.error:
            raise self.error
        for key, resp in self.routes.items():
            if key in url:
                return resp
        raise AssertionError(f'unrouted {url}')
