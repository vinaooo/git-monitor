"""What the card shows as colored chips for a RepoStatus. Pure; the card only renders it."""
from collections import namedtuple

Chip = namedtuple('Chip', 'text css tooltip')

_CI = (('failure', '✗ {n} failing', 'error'), ('running', '● {n} running', 'accent'),
       ('cancelled', '⚠ {n} cancelled', 'warning'), ('success', '✓ {n} passing', 'success'))
_PR = (('changes', '✎ {n} changes', 'error'), ('failing', '✗ {n} CI failing', 'error'),
       ('conflict', '⚠ {n} conflicts', 'warning'), ('waiting', '◌ {n} waiting', 'accent'),
       ('approved', '✓ {n} ready', 'success'), ('draft', '{n} draft', 'dim-label'))


def _chips(table, counts, details, prefix=''):
    return [Chip(text.format(n=counts[key]), css, '\n'.join(details.get(prefix + key, [])))
            for key, text, css in table if counts.get(key)]


def chips_for(s):
    """-> [(group name, [Chip])]; empty for a status without data."""
    if s is None or s.error:
        return []
    ci = _chips(_CI, s.ci_counts or {}, s.details, 'ci-') or [Chip('No CI', 'dim-label', '')]
    counts = s.pr_counts or {}
    if not s.pr_detail:
        pr = [Chip(f'{s.prs} open', 'dim-label', '')] + _chips(_PR[-1:], counts, s.details)
        pr.append(Chip('no review detail · add a token', 'dim-label', 'Review states need a GitHub token (Preferences)'))
    else:
        pr = _chips(_PR, counts, s.details) or [Chip('No open PRs', 'dim-label', '')]
    return [('CI', ci), ('PRs', pr)]
