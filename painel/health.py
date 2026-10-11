"""Pure CI / PR-MR health logic shared by the providers and the card UI."""

CI_ORDER = ('failure', 'running', 'cancelled', 'success')  # worst first
PR_BUCKETS = ('changes', 'failing', 'conflict', 'waiting', 'approved', 'draft')
TOOLTIP_LIMIT = 5


def summarize_ci(runs, running_total=None):
    """runs: newest-first [{key, state, label}]. Latest run per key counts.
    running_total: runs in progress anywhere (other branches too), raises the running count.
    Returns (counts, details {state: [labels]}, worst state)."""
    counts, details, seen = dict.fromkeys(CI_ORDER, 0), {s: [] for s in CI_ORDER}, set()
    for r in runs:
        if r['key'] in seen:
            continue
        seen.add(r['key'])
        if r['state'] in counts:
            counts[r['state']] += 1
            details[r['state']].append(r['label'])
    if running_total is not None:
        counts['running'] = max(counts['running'], running_total)
    worst = next((s for s in CI_ORDER if counts[s]), 'none')
    return counts, {s: v[:TOOLTIP_LIMIT] for s, v in details.items() if v}, worst


def pr_bucket_github(node):
    """GraphQL PullRequest node -> bucket. Order = priority: draft > changes > failing > conflict > approved > waiting."""
    if node.get('isDraft'):
        return 'draft'
    decision = node.get('reviewDecision')
    if decision == 'CHANGES_REQUESTED':
        return 'changes'
    commits = (node.get('commits') or {}).get('nodes') or []
    rollup = (commits[0]['commit'].get('statusCheckRollup') or {}) if commits else {}
    if rollup.get('state') in ('FAILURE', 'ERROR'):
        return 'failing'
    if node.get('mergeable') == 'CONFLICTING':
        return 'conflict'
    return 'approved' if decision == 'APPROVED' else 'waiting'


_GITLAB = {'mergeable': 'approved', 'requested_changes': 'changes', 'discussions_not_resolved': 'changes',
           'conflict': 'conflict', 'need_rebase': 'conflict', 'ci_must_pass': 'failing'}


def pr_bucket_gitlab(mr):
    if mr.get('draft'):
        return 'draft'
    return _GITLAB.get(mr.get('detailed_merge_status'), 'waiting')


def summarize_prs(labelled):
    """[(bucket, label)] -> (counts per bucket, details {bucket: [labels]} capped for tooltips)."""
    counts, details = dict.fromkeys(PR_BUCKETS, 0), {}
    for bucket, label in labelled:
        counts[bucket] += 1
        details.setdefault(bucket, []).append(label)
    return counts, {b: v[:TOOLTIP_LIMIT] for b, v in details.items()}


def severity(status):
    """Card health: error > warning > accent > success > none."""
    if status is None or status.error:
        return 'none'
    ci, pr = status.ci_counts or {}, status.pr_counts or {}
    if ci.get('failure') or pr.get('changes') or pr.get('failing'):
        return 'error'
    if ci.get('cancelled') or pr.get('conflict'):
        return 'warning'
    if ci.get('running'):
        return 'accent'
    return 'success' if ci.get('success') or pr.get('approved') else 'none'
