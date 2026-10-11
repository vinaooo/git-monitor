import json
import urllib.error
import urllib.request


class HttpError(Exception):
    def __init__(self, code):
        super().__init__(f'HTTP {code}')
        self.code = code


class NetworkError(Exception):
    pass


class HttpClient:
    """Port: GET url -> (parsed json, response headers). Raises HttpError / NetworkError."""

    def get(self, url, headers=None):
        raise NotImplementedError


class UrllibClient(HttpClient):
    def get(self, url, headers=None):
        req = urllib.request.Request(url, headers={'User-Agent': 'painel', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.load(r), r.headers
        except urllib.error.HTTPError as e:
            raise HttpError(e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise NetworkError(getattr(e, 'reason', e)) from e
