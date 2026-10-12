import unittest

from painel.status import RepoStatus
from painel.virtual import DEFINITIONS, members, shown

BY_ID = {d.id: d for d in DEFINITIONS}


def st(**kw):
    return RepoStatus(name='n', **kw)


class VirtualTest(unittest.TestCase):
    def test_host_groups_need_no_status(self):
        self.assertTrue(BY_ID['github'].match('github.com/o/r', None))
        self.assertFalse(BY_ID['github'].match('gitlab.com/g/p', None))
        self.assertTrue(BY_ID['gitlab'].match('gitlab.com/g/p', None))
        self.assertTrue(BY_ID['gitlab'].match('gitlab.example.org/g/p', None))
        self.assertTrue(BY_ID['forgejo'].match('codeberg.org/o/r', None))
        self.assertFalse(BY_ID['forgejo'].match('gitlab.com/g/p', None))
        self.assertFalse(BY_ID['gitlab'].match('codeberg.org/o/r', None))

    def test_status_groups_need_a_status(self):
        for vid in ('ready', 'cancelled', 'ci-failing', 'attention', 'waiting', 'errors'):
            self.assertFalse(BY_ID[vid].match('github.com/o/r', None), vid)

    def test_status_groups(self):
        i = 'github.com/o/r'
        self.assertTrue(BY_ID['ready'].match(i, st(pr_counts={'approved': 1})))
        self.assertTrue(BY_ID['cancelled'].match(i, st(ci_counts={'cancelled': 2})))
        self.assertTrue(BY_ID['ci-failing'].match(i, st(ci_counts={'failure': 1})))
        for bucket in ('changes', 'failing', 'conflict'):
            self.assertTrue(BY_ID['attention'].match(i, st(pr_counts={bucket: 1})), bucket)
        self.assertTrue(BY_ID['waiting'].match(i, st(pr_counts={'waiting': 1})))
        self.assertTrue(BY_ID['errors'].match(i, st(error='boom')))
        self.assertFalse(BY_ID['ready'].match(i, st(pr_counts={'waiting': 1})))

    def test_review_needs_flag(self):
        self.assertTrue(BY_ID['review'].match('github.com/o/r', st(review_requested=True)))
        self.assertFalse(BY_ID['review'].match('github.com/o/r', st()))
        self.assertFalse(BY_ID['review'].match('github.com/o/r', None))

    def test_members_keep_order(self):
        items = [('github.com/a/1', None), ('gitlab.com/g/2', None), ('github.com/a/3', None)]
        self.assertEqual(members(BY_ID['github'], items), ['github.com/a/1', 'github.com/a/3'])

    def test_shown_needs_enabled_and_members(self):
        by_id = {'github': ['x'], 'gitlab': [], 'ready': ['y']}
        self.assertEqual(shown(set(), by_id), ['github', 'ready'])
        self.assertEqual(shown({'github'}, by_id), ['ready'])  # disabled ids are passed in


if __name__ == '__main__':
    unittest.main()


class CategoriesTest(unittest.TestCase):
    def test_every_definition_in_exactly_one_category(self):
        from painel.virtual import CATEGORIES, DEFINITIONS
        ids = [i for _c, _t, group in CATEGORIES for i in group]
        self.assertEqual(sorted(ids), sorted(d.id for d in DEFINITIONS))
