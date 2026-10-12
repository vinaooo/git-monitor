"""Virtual groups: read-only collections across all real groups, built from each repo's host or status. Pure."""
from collections import namedtuple

from . import repo_id

Definition = namedtuple('Definition', 'id title subtitle icon match')  # match(ident, status|None) -> bool


def _count(status, field, *keys):
    return bool(status and not status.error and any((getattr(status, field) or {}).get(k) for k in keys))


DEFINITIONS = (
    Definition('github', 'GitHub', 'Every GitHub repository', 'painel-github-symbolic',
               lambda i, s: repo_id.host_of(i) == repo_id.GITHUB_HOST),
    Definition('gitlab', 'GitLab', 'Every GitLab repository', 'painel-gitlab-symbolic',
               lambda i, s: repo_id.kind(repo_id.host_of(i)) == 'gitlab'),
    Definition('forgejo', 'Forgejo / Gitea', 'Every Forgejo or Gitea repository', 'painel-forgejo-symbolic',
               lambda i, s: repo_id.kind(repo_id.host_of(i)) == 'forgejo'),
    Definition('ready', 'PR/MR ready', 'Approved and ready to merge', 'object-select-symbolic',
               lambda i, s: _count(s, 'pr_counts', 'approved')),
    Definition('cancelled', 'CI cancelled', 'A CI run was cancelled', 'process-stop-symbolic',
               lambda i, s: _count(s, 'ci_counts', 'cancelled')),
    Definition('ci-failing', 'CI failing', 'A CI run is failing', 'dialog-error-symbolic',
               lambda i, s: _count(s, 'ci_counts', 'failure')),
    Definition('attention', 'PRs need attention', 'Changes requested, failing checks or conflicts', 'dialog-warning-symbolic',
               lambda i, s: _count(s, 'pr_counts', 'changes', 'failing', 'conflict')),
    Definition('review', 'Review requested', 'PRs/MRs waiting for my review', 'mail-unread-symbolic',
               lambda i, s: bool(s and s.review_requested)),
    Definition('waiting', 'Waiting for review', 'PRs/MRs waiting for a review', 'content-loading-symbolic',
               lambda i, s: _count(s, 'pr_counts', 'waiting')),
    Definition('errors', 'Fetch errors', 'The last refresh failed', 'network-error-symbolic',
               lambda i, s: bool(s and s.error)),
)


# sidebar sections: (id, title, virtual group ids); every definition belongs to exactly one
CATEGORIES = (
    ('services', 'Services', ('github', 'gitlab', 'forgejo')),
    ('prs', 'PR/MR', ('ready', 'attention', 'review', 'waiting')),
    ('ci', 'CI & errors', ('ci-failing', 'cancelled', 'errors')),
)


def members(definition, items):
    """Identities of `items` [(ident, status|None)] that belong to the group, in the given order."""
    return [i for i, s in items if definition.match(i, s)]


def shown(disabled, members_by_id):
    """Ids to display: not disabled and with at least one member, in DEFINITIONS order."""
    return [d.id for d in DEFINITIONS if d.id not in disabled and members_by_id.get(d.id)]
