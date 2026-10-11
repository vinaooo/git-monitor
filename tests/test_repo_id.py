import unittest

from painel.repo_id import host_of, migrate, parse


class ParseTest(unittest.TestCase):
    def test_github_forms(self):
        for text in ('https://github.com/gnome/gtk.git', 'github.com/gnome/gtk/issues?x=1', ' gnome/gtk '):
            self.assertEqual(parse(text), 'github.com/gnome/gtk', text)

    def test_gitlab_forms(self):
        self.assertEqual(parse('https://gitlab.com/g/sub/p/-/issues'), 'gitlab.com/g/sub/p')
        self.assertEqual(parse('gitlab.example.org/a/b.git'), 'gitlab.example.org/a/b')

    def test_rejects(self):
        for text in ('https://example.com/a/b', 'foo', 'a/b/c', '', 'https://github.com/onlyone'):
            self.assertIsNone(parse(text), text)

    def test_migrate_and_host(self):
        self.assertEqual(migrate('a/b'), 'github.com/a/b')
        self.assertEqual(migrate('gitlab.com/a/b'), 'gitlab.com/a/b')
        self.assertEqual(host_of('gitlab.com/a/b'), 'gitlab.com')
