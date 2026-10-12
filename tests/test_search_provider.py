import unittest
from types import SimpleNamespace as NS

from painel.search_provider import LIMIT, find


def item(ident, ci):
    return ident, ident, NS(name=ident, url=f'https://{ident}', error=None, ci_counts={ci: 1}, pr_counts={})


class FindTest(unittest.TestCase):
    ITEMS = [item('github.com/o/a', 'failure'), item('github.com/o/b', 'success')]

    def test_app_name_prefix_is_ignored(self):
        self.assertEqual(find(['painel', 'failing'], self.ITEMS), ['github.com/o/a'])

    def test_all_terms_must_match(self):
        self.assertEqual(find(['failing', 'passing'], self.ITEMS), [])

    def test_only_app_name_lists_all_capped(self):
        many = [item(f'github.com/o/r{n}', 'success') for n in range(LIMIT + 5)]
        self.assertEqual(len(find(['Painel'], many)), LIMIT)
