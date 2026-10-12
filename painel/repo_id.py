"""Repo identity = 'host/path' (e.g. 'github.com/o/r', 'gitlab.com/g/sub/p')."""
import re

GITHUB_HOST = 'github.com'
_URL = re.compile(r'^(?:https?://)?(?:www\.)?([\w.-]+\.[\w.-]+)/(.+)$')
_BARE = re.compile(r'^([\w.-]+)/([\w.-]+?)(?:\.git)?$')


def is_gitlab_host(host):
    return host == 'gitlab.com' or host.startswith('gitlab.')


def parse(text):
    """URL, 'host/path' or bare 'o/r' (= GitHub) -> identity, else None."""
    text = text.strip()
    m = _URL.match(text)
    if m:
        host = m[1].lower()
        path = re.sub(r'\.git$', '', re.split(r'[?#]|/-/', m[2])[0].strip('/'))
        if host == GITHUB_HOST:
            parts = path.split('/')
            return f'{host}/{parts[0]}/{parts[1]}' if len(parts) >= 2 and all(parts[:2]) else None
        if is_gitlab_host(host) and '/' in path and re.fullmatch(r'[\w./-]+', path):
            return f'{host}/{path}'
        return None
    m = _BARE.match(text)
    return f'{GITHUB_HOST}/{m[1]}/{m[2]}' if m else None


def migrate(ident):
    """Legacy stored 'owner/name' -> 'github.com/owner/name'."""
    return ident if '.' in ident.split('/')[0] else f'{GITHUB_HOST}/{ident}'


def host_of(ident):
    return ident.split('/')[0]


_NAME = re.compile(r'[\w.-]+')


def parse_account(text, default_host=GITHUB_HOST):
    """User/org URL, 'host/account' or bare name (-> `default_host`) -> (host, account), else None.
    GitLab accounts may be groups with subgroups ('g/sub'); a GitHub 'owner/repo' is a repo, not an account."""
    text = text.strip().lstrip('@')
    if _NAME.fullmatch(text) and not _URL.match(text + '/x'):  # 'github.com' alone is a host, not a name
        return default_host, text
    m = _URL.match(text)
    if not m:
        return None
    host = m[1].lower()
    path = re.split(r'[?#]|/-/', m[2])[0].strip('/')
    if host == GITHUB_HOST:
        return (host, path) if _NAME.fullmatch(path) else None
    if is_gitlab_host(host) and re.fullmatch(r'[\w.-]+(/[\w.-]+)*', path):
        return host, path
    return None
