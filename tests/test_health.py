import unittest

from painel.health import pr_bucket_github, pr_bucket_gitlab, severity, summarize_ci, summarize_prs
from painel.status import RepoStatus


def run(key, state, label=None):
    return {'key': key, 'state': state, 'label': label or key}


class CiSummaryTest(unittest.TestCase):
    def test_latest_run_per_key_counts(self):
        runs = [run('build', 'failure'), run('build', 'success'),   # older build run ignored
                run('lint', 'success'), run('deploy', 'running')]
        counts, details, worst = summarize_ci(runs)
        self.assertEqual(counts, {'failure': 1, 'running': 1, 'cancelled': 0, 'success': 1})
        self.assertEqual(details['failure'], ['build'])
        self.assertEqual(worst, 'failure')

    def test_worst_order(self):
        self.assertEqual(summarize_ci([run('a', 'running'), run('b', 'success')])[2], 'running')
        self.assertEqual(summarize_ci([run('a', 'cancelled'), run('b', 'success')])[2], 'cancelled')
        self.assertEqual(summarize_ci([run('a', 'success')])[2], 'success')
        self.assertEqual(summarize_ci([])[2], 'none')

    def test_running_total_elsewhere_raises_running_count(self):
        counts, _, worst = summarize_ci([run('a', 'success')], running_total=3)
        self.assertEqual((counts['running'], worst), (3, 'running'))
        self.assertEqual(summarize_ci([run('a', 'running')], running_total=0)[0]['running'], 1)

    def test_unknown_state_is_ignored(self):
        self.assertEqual(summarize_ci([run('a', 'weird')])[2], 'none')


class PrBucketTest(unittest.TestCase):
    def gh(self, **kw):
        node = {'isDraft': False, 'reviewDecision': None, 'mergeable': 'MERGEABLE',
                'commits': {'nodes': [{'commit': {'statusCheckRollup': {'state': 'SUCCESS'}}}]}}
        node.update(kw)
        return pr_bucket_github(node)

    def test_github_buckets(self):
        self.assertEqual(self.gh(), 'approved')  # default node: green checks, no review rule
        self.assertEqual(self.gh(reviewDecision='APPROVED'), 'approved')
        self.assertEqual(self.gh(reviewDecision='REVIEW_REQUIRED'), 'waiting')
        self.assertEqual(self.gh(reviewDecision='CHANGES_REQUESTED'), 'changes')
        self.assertEqual(self.gh(mergeable='CONFLICTING'), 'conflict')
        self.assertEqual(self.gh(isDraft=True), 'draft')

    def test_github_priority_and_checks(self):
        self.assertEqual(self.gh(isDraft=True, mergeable='CONFLICTING'), 'draft')
        self.assertEqual(self.gh(reviewDecision='CHANGES_REQUESTED', mergeable='CONFLICTING'), 'changes')
        failing = {'nodes': [{'commit': {'statusCheckRollup': {'state': 'FAILURE'}}}]}
        self.assertEqual(self.gh(reviewDecision='APPROVED', commits=failing), 'failing')
        self.assertEqual(self.gh(commits={'nodes': []}, reviewDecision='APPROVED'), 'approved')
        self.assertEqual(self.gh(commits={'nodes': [{'commit': {'statusCheckRollup': None}}]}), 'waiting')

    def test_github_green_without_review_rule_is_ready(self):
        green = {'nodes': [{'commit': {'statusCheckRollup': {'state': 'SUCCESS'}}}]}
        self.assertEqual(self.gh(commits=green), 'approved')  # reviewDecision null: no rule, nothing to wait for
        self.assertEqual(self.gh(commits=green, reviewDecision='REVIEW_REQUIRED'), 'waiting')

    def test_gitlab_buckets(self):
        for status, bucket in (('mergeable', 'approved'), ('requested_changes', 'changes'),
                               ('discussions_not_resolved', 'changes'), ('conflict', 'conflict'),
                               ('need_rebase', 'conflict'), ('ci_must_pass', 'failing'),
                               ('not_approved', 'waiting'), ('ci_still_running', 'waiting'),
                               ('something_new', 'waiting'), (None, 'waiting')):
            self.assertEqual(pr_bucket_gitlab({'detailed_merge_status': status}), bucket, status)
        self.assertEqual(pr_bucket_gitlab({'draft': True, 'detailed_merge_status': 'conflict'}), 'draft')

    def test_summarize_prs(self):
        counts, details = summarize_prs([('approved', '#1 a'), ('approved', '#2 b'), ('draft', '#3 c')] +
                                        [('waiting', f'#{n}') for n in range(10, 17)])
        self.assertEqual(counts, {'changes': 0, 'failing': 0, 'conflict': 0, 'waiting': 7, 'approved': 2, 'draft': 1})
        self.assertEqual(details['approved'], ['#1 a', '#2 b'])
        self.assertEqual(len(details['waiting']), 5)  # tooltips capped


class SeverityTest(unittest.TestCase):
    def sev(self, ci=None, prs=None, **kw):
        base = dict(failure=0, running=0, cancelled=0, success=0)
        base.update(ci or {})
        pr = dict(changes=0, failing=0, conflict=0, waiting=0, approved=0, draft=0)
        pr.update(prs or {})
        return severity(RepoStatus(name='x', ci_counts=base, pr_counts=pr, **kw))

    def test_matrix(self):
        self.assertEqual(self.sev({'failure': 1, 'running': 2}), 'error')       # failing beats running
        self.assertEqual(self.sev({'success': 2}, {'changes': 1}), 'error')
        self.assertEqual(self.sev({'success': 2}, {'failing': 1}), 'error')
        self.assertEqual(self.sev({'cancelled': 1, 'success': 1}), 'warning')
        self.assertEqual(self.sev({'success': 1}, {'conflict': 1}), 'warning')
        self.assertEqual(self.sev({'running': 1, 'success': 1}), 'accent')
        self.assertEqual(self.sev({'success': 3}, {'approved': 1, 'waiting': 2}), 'success')
        self.assertEqual(self.sev({}, {'draft': 2}), 'none')

    def test_error_or_empty_status_has_no_color(self):
        self.assertEqual(severity(RepoStatus(name='x', error='Not found')), 'none')
        self.assertEqual(severity(RepoStatus(name='x')), 'none')
        self.assertEqual(severity(None), 'none')

    def test_anonymous_github_never_claims_approved(self):
        self.assertEqual(self.sev({}, {'draft': 1}, pr_detail=False), 'none')


class GroupSeverityTest(unittest.TestCase):
    def test_worst_card_wins(self):
        from painel.health import group_severity
        self.assertEqual(group_severity(['success', 'error', 'accent']), 'error')
        self.assertEqual(group_severity(['success', 'accent']), 'accent')
        self.assertEqual(group_severity(['warning', 'accent']), 'warning')
        self.assertEqual(group_severity(['none', 'success']), 'success')

    def test_empty_or_unknown_is_none(self):
        from painel.health import group_severity
        self.assertEqual(group_severity([]), 'none')
        self.assertEqual(group_severity(['none', 'none']), 'none')
