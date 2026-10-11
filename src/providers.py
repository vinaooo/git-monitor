import json
import re
import urllib.error
import urllib.parse
import urllib.request

import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

_SCHEMA = Secret.Schema.new('io.github.vina.Painel', Secret.SchemaFlags.NONE,
                            {'purpose': Secret.SchemaAttributeType.STRING,
                             'host': Secret.SchemaAttributeType.STRING})
_URL = re.compile(r'^(?:https?://)?(?:www\.)?([\w.-]+\.[\w.-]+)/(.+)$')
_BARE = re.compile(r'^([\w.-]+)/([\w.-]+?)(?:\.git)?$')


def _is_gitlab(host):
    return host == 'gitlab.com' or host.startswith('gitlab.')


def parse(text):
    """URL, 'host/path' or bare 'o/r' (=GitHub) -> 'host/path' identity; else None."""
    text = text.strip()
    m = _URL.match(text)
    if m:
        host, rest = m[1].lower(), re.split(r'[?#]|/-/', m[2])[0].strip('/')
        rest = re.sub(r'\.git$', '', rest)
        if host == 'github.com':
            parts = rest.split('/')
            return f'{host}/{parts[0]}/{parts[1]}' if len(parts) >= 2 and all(parts[:2]) else None
        if _is_gitlab(host) and rest.count('/') >= 1 and re.fullmatch(r'[\w./-]+', rest):
            return f'{host}/{rest}'
        return None
    m = _BARE.match(text)
    return f'github.com/{m[1]}/{m[2]}' if m else None


def migrate(ident):
    """Legacy stored 'owner/name' -> 'github.com/owner/name'."""
    return ident if '.' in ident.split('/')[0] else f'github.com/{ident}'


def host_of(ident):
    return ident.split('/')[0]


def get_token(host):
    t = Secret.password_lookup_sync(_SCHEMA, {'host': host}, None)
    if t is None and host == 'github.com':  # token saved before multi-host support
        t = Secret.password_lookup_sync(_SCHEMA, {'purpose': 'github-token'}, None)
    return t


def set_token(host, token):
    if token:
        Secret.password_store_sync(_SCHEMA, {'host': host}, Secret.COLLECTION_DEFAULT,
                                   f'Painel token for {host}', token, None)
    else:
        Secret.password_clear_sync(_SCHEMA, {'host': host}, None)


def _get(url, headers, want_headers=False):
    req = urllib.request.Request(url, headers={'User-Agent': 'painel', **headers})
    with urllib.request.urlopen(req, timeout=15) as r:
        body = json.load(r)
        return (body, r.headers) if want_headers else body


def _github(path, token):
    h = {'Accept': 'application/vnd.github+json'}
    if token:
        h['Authorization'] = f'Bearer {token}'
    full = path
    repo = _get(f'https://api.github.com/repos/{full}', h)
    prs = _get(f'https://api.github.com/search/issues?q=repo:{full}+type:pr+state:open&per_page=1', h)['total_count']
    runs = _get(f'https://api.github.com/repos/{full}/actions/runs?per_page=1', h)['workflow_runs']
    if not runs:
        ci = 'none'
    elif runs[0]['status'] != 'completed':
        ci = 'running'
    else:
        ci = runs[0]['conclusion'] or 'none'
    return dict(name=repo['full_name'], url=repo['html_url'], ci=ci, prs=prs,
                issues=repo['open_issues_count'] - prs)  # API count includes PRs


_GL_CI = {'success': 'success', 'failed': 'failure', 'canceled': 'cancelled',
          'running': 'running', 'pending': 'running', 'created': 'running', 'preparing': 'running',
          'waiting_for_resource': 'running', 'scheduled': 'running'}


def _gitlab(host, path, token):
    h = {'PRIVATE-TOKEN': token} if token else {}
    base = f'https://{host}/api/v4/projects/{urllib.parse.quote(path, safe="")}'
    p = _get(base, h)
    _, hdr = _get(f'{base}/merge_requests?state=opened&per_page=1', h, True)
    mrs = int(hdr.get('X-Total') or 0)  # header omitted above 10000 results
    issues = _get(f'{base}/issues_statistics', h)['statistics']['counts']['opened']  # open_issues_count is absent for anonymous calls
    pipes = _get(f'{base}/pipelines?per_page=1', h)
    return dict(name=p['name_with_namespace'].replace(' / ', '/'), url=p['web_url'], prs=mrs,
                issues=issues,
                ci=_GL_CI.get(pipes[0]['status'], 'none') if pipes else 'none')


def fetch(ident, token):
    """Blocking. Returns dict(name, url, issues, prs, ci) or dict(name, error)."""
    host, _, path = ident.partition('/')
    try:
        return _github(path, token) if host == 'github.com' else _gitlab(host, path, token)
    except urllib.error.HTTPError as e:
        msg = {404: 'Not found (private? add a token)', 401: 'Invalid token',
               403: 'Forbidden or rate limited (add a token)', 429: 'Rate limited (add a token)'}
        return dict(name=path, error=msg.get(e.code, f'HTTP {e.code}'))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return dict(name=path, error=f'Network error: {getattr(e, "reason", e)}')
    except (KeyError, IndexError, ValueError, TypeError):
        return dict(name=path, error='Unexpected API response')


if __name__ == '__main__':
    assert parse('https://github.com/gnome/gtk.git') == 'github.com/gnome/gtk'
    assert parse('github.com/gnome/gtk/issues?x=1') == 'github.com/gnome/gtk'
    assert parse(' gnome/gtk ') == 'github.com/gnome/gtk'
    assert parse('https://gitlab.com/g/sub/p/-/issues') == 'gitlab.com/g/sub/p'
    assert parse('gitlab.example.org/a/b.git') == 'gitlab.example.org/a/b'
    assert parse('https://example.com/a/b') is None
    assert parse('foo') is None and parse('a/b/c') is None and parse('') is None
    assert migrate('a/b') == 'github.com/a/b' and migrate('gitlab.com/a/b') == 'gitlab.com/a/b'
    print('ok')
