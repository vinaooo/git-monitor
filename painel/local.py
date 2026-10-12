"""State of a linked local clone: branch, ahead/behind, dirty. Read-only git, nothing is sent anywhere.

Ahead/behind come from the remote-tracking refs already on disk, so they are as fresh as the clone's last fetch.
Pure parsing + one subprocess boundary (`run_git`), injectable for tests."""
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .chips import Chip, age_days

STALE_DAYS = 7
TIMEOUT = 10  # seconds per git call; huge repos / slow FUSE report 'timeout' instead of hanging a worker
READ_ONLY = frozenset({'status', 'symbolic-ref', 'config'})  # the only git subcommands this module may run
_ENV = {'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1', 'LC_ALL': 'C'}
# core.fsmonitor from the repo's own config would run an arbitrary command during `status`; safe.directory='*'
# because a document-portal folder can look foreign-owned and we only ever read
_BASE = ('-c', 'core.fsmonitor=false', '-c', 'safe.directory=*', '--no-optional-locks')

ERRORS = {'missing': 'clone folder missing', 'nogit': 'git not found', 'unsupported': 'worktree/submodule not supported',
          'timeout': 'local check timed out', 'failed': 'local check failed'}


@dataclass(frozen=True)
class LocalState:
    branch: Optional[str] = None       # None = detached HEAD
    oid: str = ''                      # short commit id, shown when detached
    upstream: Optional[str] = None
    ahead: Optional[int] = None        # None = no tracking info (no upstream, or it is gone)
    behind: Optional[int] = None
    dirty: int = 0                     # tracked files with changes (staged, unstaged or unmerged)
    untracked: int = 0
    default_branch: Optional[str] = None
    fetched_at: Optional[float] = None  # epoch mtime of .git/FETCH_HEAD
    error: Optional[str] = None        # key of ERRORS


def parse_status(text):
    """`git status --porcelain=v2 --branch` output -> LocalState (without default_branch / fetched_at)."""
    f = {'branch': None, 'oid': '', 'upstream': None, 'ahead': None, 'behind': None, 'dirty': 0, 'untracked': 0}
    for line in text.splitlines():
        if line.startswith('# branch.oid '):
            f['oid'] = line[13:20]
        elif line.startswith('# branch.head '):
            head = line[14:]
            f['branch'] = None if head == '(detached)' else head
        elif line.startswith('# branch.upstream '):
            f['upstream'] = line[18:]
        elif line.startswith('# branch.ab '):
            plus, minus = line[12:].split()
            f['ahead'], f['behind'] = int(plus[1:]), int(minus[1:])
        elif line[:2] in ('1 ', '2 ', 'u '):
            f['dirty'] += 1
        elif line.startswith('? '):
            f['untracked'] += 1
    return LocalState(**f)


def origin_matches(url, ident):
    """Does a clone's origin URL (https, ssh or scp style) point at the repo `ident` (`host/path`)?"""
    u = re.sub(r'^[a-z+]+://', '', url.strip().lower())
    u = re.sub(r'^[^@/]*@', '', u)
    u = re.sub(r':(\d+/)?', '/', u, count=1)  # scp 'host:path' or 'host:22/path'
    return re.sub(r'(\.git)?/*$', '', u) == ident.lower()


def run_git(args, cwd):
    """-> (returncode, stdout). Raises FileNotFoundError (no git), subprocess.TimeoutExpired."""
    assert args[0] in READ_ONLY, args
    git = shutil.which('git')
    if not git:
        raise FileNotFoundError('git')
    # explicit dirs + a neutral cwd: inside a document-portal FUSE folder git loses track of the work tree
    # ("must be run in a work tree") when it discovers it from the cwd
    where = ('--git-dir', os.path.join(cwd, '.git'), '--work-tree', cwd)
    done = subprocess.run([git, *_BASE, *where, *args], cwd='/', env={**os.environ, **_ENV}, capture_output=True, text=True,
                          timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    return done.returncode, done.stdout


def inspect(folder, run=run_git):
    """LocalState of the clone in `folder`; failures come back as `error`, never raise."""
    git_dir = os.path.join(folder, '.git')
    if not os.path.isdir(folder):
        return LocalState(error='missing')
    if os.path.isfile(git_dir):  # `.git` file = worktree/submodule, points at a host path the sandbox cannot see
        return LocalState(error='unsupported')
    if not os.path.isdir(git_dir):
        return LocalState(error='failed')
    try:
        code, out = run(('status', '--porcelain=v2', '--branch', '--untracked-files=normal', '--ignore-submodules=all'), folder)
        if code:
            return LocalState(error='failed')
        state = parse_status(out)
        code, head = run(('symbolic-ref', '-q', '--short', 'refs/remotes/origin/HEAD'), folder)
        default = head.strip().partition('/')[2] or None if code == 0 else None
    except FileNotFoundError:
        return LocalState(error='nogit')
    except subprocess.TimeoutExpired:
        return LocalState(error='timeout')
    except OSError:
        return LocalState(error='failed')
    try:
        fetched = os.stat(os.path.join(git_dir, 'FETCH_HEAD')).st_mtime
    except OSError:
        fetched = None
    return LocalState(**{**state.__dict__, 'default_branch': default, 'fetched_at': fetched})


def origin_url(folder, run=run_git):
    try:
        code, out = run(('config', '--get', 'remote.origin.url'), folder)
    except (OSError, subprocess.SubprocessError):
        return ''
    return out.strip() if code == 0 else ''


def words(s):
    """Search words for a state, worded like the chips."""
    if s is None or s.error:
        return ''
    found = ['local', 'dirty' if s.dirty else 'clean']
    if s.untracked:
        found.append('untracked')
    if s.branch is None:
        found.append('detached')
    if s.behind:
        found.append('behind outdated')
    if s.ahead:
        found.append('ahead unpushed')
    if s.ahead and s.behind:
        found.append('diverged')
    return ' '.join(found)


def chips(s, now=None):
    """-> [Chip] for the card's Git row; [] when the clone is not linked (`s` None)."""
    if s is None:
        return []
    if s.error:
        return [Chip(ERRORS[s.error], 'warning' if s.error in ('missing', 'unsupported') else 'dim-label',
                     'Relink the folder from the card menu' if s.error == 'missing' else '')]
    now = now or datetime.now(timezone.utc)
    days = None if s.fetched_at is None else age_days(datetime.fromtimestamp(s.fetched_at, timezone.utc).isoformat(), now)
    note = 'Local clone. Counts use the last fetch, not the live remote.' + ('' if days is None else f'\nLast fetch: {"today" if days < 1 else f"{days}d ago"}')
    out = []
    if s.branch is None:
        out.append(Chip(f'⎇ detached {s.oid}', 'warning', note))
    else:
        off = s.default_branch is not None and s.branch != s.default_branch
        out.append(Chip(f'⎇ {s.branch}', 'warning' if off else 'dim-label',
                        note + (f'\nNot the default branch ({s.default_branch})' if off else '')))
    if s.upstream is None:
        out.append(Chip('no upstream', 'dim-label', note))
    elif s.ahead is None:
        out.append(Chip('upstream gone', 'warning', note))
    if s.ahead:
        out.append(Chip(f'↑{s.ahead} ahead', 'accent', f'{s.ahead} unpushed commit(s) vs {s.upstream}\n{note}'))
    if s.behind:
        out.append(Chip(f'↓{s.behind} outdated', 'warning', f'{s.behind} commit(s) behind {s.upstream}\n{note}'))
    if s.dirty:
        out.append(Chip(f'✎ {s.dirty} changed', 'warning', 'Uncommitted changes in tracked files'))
    if s.untracked:
        out.append(Chip(f'? {s.untracked} untracked', 'dim-label', 'Untracked files'))
    if len(out) == 1 and s.upstream and s.ahead == 0 and s.behind == 0 and not s.dirty and not s.untracked:
        out.append(Chip('✓ clean', 'success', note))
    if days and days >= STALE_DAYS:  # compact: the age lives in the tooltips, a chip only when it is stale
        out.append(Chip(f'fetched {days}d ago', 'warning', note))
    return out
