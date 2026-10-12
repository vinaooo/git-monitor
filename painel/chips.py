"""What the card shows as colored chips for a RepoStatus. Pure; the card only renders it."""
from collections import namedtuple
from datetime import datetime, timezone
from urllib.parse import urlsplit

from . import repo_id

Chip = namedtuple('Chip', 'text css tooltip url', defaults=('',))  # url: where a click goes ('' = not clickable)

_CI = (('failure', '✗ {n} failing', 'error'), ('running', '● {n} running', 'accent'),
       ('cancelled', '⚠ {n} cancelled', 'warning'), ('success', '✓ {n} passing', 'success'))
_PR = (('changes', '✎ {n} changes', 'error'), ('failing', '✗ {n} CI failing', 'error'),
       ('conflict', '⚠ {n} conflicts', 'warning'), ('waiting', '◌ {n} waiting', 'accent'),
       ('approved', '✓ {n} ready', 'success'), ('draft', '{n} draft', 'dim-label'))


_GITHUB_QUERY = {'draft': 'draft%3Atrue', 'approved': 'status%3Asuccess+-review%3Arequired', 'changes': 'review%3Achanges_requested',
                 'waiting': 'review%3Arequired+draft%3Afalse', 'failing': 'status%3Afailure'}
_GITLAB_QUERY = {'draft': '&draft=yes', 'approved': '&draft=no', 'waiting': '&draft=no'}  # no review-state filters


def url_kind(url):
    """Provider of a repo web URL (see repo_id.kind); anything unrecognised reads as GitLab, as before."""
    return repo_id.kind(urlsplit(url).hostname or '') or 'gitlab'


def pr_list_url(base, bucket):
    """The repo's open PR/MR list, filtered as far as the platform's URL search allows."""
    if not base:
        return ''
    kind = url_kind(base)
    if kind == 'forgejo':
        return f'{base}/pulls?state=open'
    if kind == 'github':
        extra = _GITHUB_QUERY.get(bucket)
        return f'{base}/pulls?q=is%3Apr+is%3Aopen' + (f'+{extra}' if extra else '')
    return f'{base}/-/merge_requests?state=opened' + _GITLAB_QUERY.get(bucket, '')


def _chips(table, counts, details, prefix='', link=None):
    return [Chip(text.format(n=counts[key]), css, '\n'.join(details.get(prefix + key, [])), link(key) if link else '')
            for key, text, css in table if counts.get(key)]


def age_days(iso, now):
    """Whole days from the ISO time `iso` to `now`; None if it does not parse."""
    try:
        return (now - datetime.fromisoformat(iso.replace('Z', '+00:00'))).days
    except (ValueError, AttributeError, TypeError):
        return None


def _ago(iso, now):
    days = age_days(iso, now)
    return None if days is None else 'today' if days < 1 else f'{days}d ago'


def _repo_chips(s, now):
    """Optional signal chips; each appears only when its data is there and non-trivial."""
    chips = []
    alerts = (s.dependabot or 0) + (s.code_scanning or 0)
    if alerts:
        more = '+' if (s.code_scanning or 0) >= 100 else ''
        chips.append(Chip(f'⛨ {alerts}{more} alerts', 'warning', f'Dependabot {s.dependabot or 0} · Code scanning {s.code_scanning or 0}',
                          f'{s.url}/security' if s.url else ''))
    if s.release and (age := _ago(s.released_at, now)):
        chips.append(Chip(f'⬆ {s.release} · {age}', 'dim-label', 'Latest release', f'{s.url}/releases' if s.url else ''))
    if s.pushed_at and (age := _ago(s.pushed_at, now)):
        chips.append(Chip(f'pushed {age}', 'dim-label', 'Last push'))
    return chips


def chips_for(s, now=None):
    """-> [(group name, [Chip])]; empty for a status without data. `now` is injectable for tests."""
    if s is None or s.error:
        return []
    ci = _chips(_CI, s.ci_counts or {}, s.details, 'ci-') or [Chip('No CI', 'dim-label', '')]
    counts = s.pr_counts or {}
    link = lambda bucket: pr_list_url(s.url, bucket)
    if not s.pr_detail:
        pr = [Chip(f'{s.prs} open', 'dim-label', '', pr_list_url(s.url, 'open'))] + _chips(_PR[-1:], counts, s.details, link=link)
        pr.append(Chip('no review detail · add a token', 'dim-label', 'Review states need a GitHub token (Preferences)'))
    else:
        pr = _chips(_PR, counts, s.details, link=link) or [Chip('No open PRs', 'dim-label', '')]
    if s.unresolved:
        pr.append(Chip(f'💬 {s.unresolved} unresolved', 'warning', '\n'.join(s.details.get('unresolved', []))))
    repo = _repo_chips(s, now or datetime.now(timezone.utc))
    return [('CI', ci), ('PRs', pr)] + ([('Repo', repo)] if repo else [])
