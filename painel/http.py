import collections
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class HttpError(Exception):
    def __init__(self, code, headers=None):
        super().__init__(f'HTTP {code}')
        self.code, self.headers = code, headers  # headers: of the error response (Retry-After, rate limit)


class NetworkError(Exception):
    pass


class HttpClient:
    """Port: GET url -> (parsed json, response headers). Raises HttpError / NetworkError."""

    def get(self, url, headers=None):
        raise NotImplementedError

    def post(self, url, body, headers=None):
        """POST a JSON body (GraphQL)."""
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
        return self._send(urllib.request.Request(url, headers={'User-Agent': 'painel', **(headers or {})}))

    def post(self, url, body, headers=None):
        return self._send(urllib.request.Request(
            url, data=json.dumps(body).encode(), method='POST',
            headers={'User-Agent': 'painel', 'Content-Type': 'application/json', **(headers or {})}))

    def _send(self, req):
        try:
            with _opener.open(req, timeout=15) as r:
                return json.load(r), r.headers
        except urllib.error.HTTPError as e:
            e.close()  # headers stay readable; frees the socket (a 304 has no body to read)
            raise HttpError(e.code, e.headers) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise NetworkError(getattr(e, 'reason', e)) from e


def _int(headers, *names):
    for name in names:
        try:
            return int(headers.get(name))
        except (TypeError, ValueError):
            pass
    return None


class RateState:
    """Per host: how long the server asked us to stay away. Fed from response headers: `Retry-After`,
    `X-Poll-Interval` (a floor between polls) and an exhausted quota (`X-RateLimit-*` on GitHub, `RateLimit-*` on GitLab)."""

    def __init__(self, clock=time.time):
        self.clock, self.until = clock, {}

    def note(self, url, headers):
        if headers is None:
            return
        now, wait = self.clock(), _int(headers, 'Retry-After', 'X-Poll-Interval') or 0
        if _int(headers, 'X-RateLimit-Remaining', 'RateLimit-Remaining') == 0:
            reset = _int(headers, 'X-RateLimit-Reset', 'RateLimit-Reset')
            wait = max(wait, (reset or now) - now)
        self.until[urllib.parse.urlsplit(url).netloc] = now + wait

    def wait(self, host):
        """Seconds until `host` may be asked again (0 = now)."""
        return max(0, self.until.get(host, 0) - self.clock())


class CachingClient(HttpClient):
    """Conditional GETs (ETag / If-Modified-Since): a 304 is answered from memory and is free on GitHub's
    primary rate limit. In-memory only (responses can be private), keyed per credential so a token change never
    reuses another token's data. Also keeps the `RateState` and the recent share of 304s."""

    SAMPLES = 300  # ponytail: rolling window of the last GETs; per-host ratios if hosts differ a lot

    def __init__(self, inner, state=None, size=512, min_samples=30):
        self.inner, self.state, self.size, self.min_samples = inner, state or RateState(), size, min_samples
        self.cache, self.lock = collections.OrderedDict(), threading.Lock()
        self.outcomes = collections.deque(maxlen=self.SAMPLES)  # True = served by a 304

    def get(self, url, headers=None):
        headers = dict(headers or {})
        key = (url, hash((headers.get('Authorization'), headers.get('PRIVATE-TOKEN'))))
        with self.lock:
            hit = self.cache.get(key)
        if hit:
            etag, modified, _, _ = hit
            if etag:
                headers['If-None-Match'] = etag
            if modified:
                headers['If-Modified-Since'] = modified
        try:
            body, hdr = self.inner.get(url, headers)
        except HttpError as e:
            self.state.note(url, e.headers)
            if e.code == 304 and hit:
                self.outcomes.append(True)
                return hit[2], hit[3]
            raise
        self.outcomes.append(False)
        self.state.note(url, hdr)
        etag, modified = hdr.get('ETag'), hdr.get('Last-Modified')
        if etag or modified:
            with self.lock:
                self.cache[key] = (etag, modified, body, hdr)
                self.cache.move_to_end(key)
                while len(self.cache) > self.size:
                    self.cache.popitem(last=False)
        return body, hdr

    def post(self, url, body, headers=None):
        resp = self.inner.post(url, body, headers)
        self.state.note(url, resp[1])
        return resp

    def hit_ratio(self):
        """Share of recent GETs answered by a 304; 0 until there are enough samples (worst case for estimates)."""
        n = len(self.outcomes)
        return sum(self.outcomes) / n if n >= self.min_samples else 0.0
