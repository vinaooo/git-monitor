import json
import urllib.error
import urllib.parse
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


_CREDENTIAL_HEADERS = ('authorization', 'private-token')


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """urllib forwards every header on redirect; drop credentials when the host changes."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            for name in _CREDENTIAL_HEADERS:
                new.headers.pop(name.capitalize(), None)
        return new


_opener = urllib.request.build_opener(_SafeRedirect)


class UrllibClient(HttpClient):
    def get(self, url, headers=None):
        req = urllib.request.Request(url, headers={'User-Agent': 'painel', **(headers or {})})
        try:
            with _opener.open(req, timeout=15) as r:
                return json.load(r), r.headers
        except urllib.error.HTTPError as e:
            raise HttpError(e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise NetworkError(getattr(e, 'reason', e)) from e
