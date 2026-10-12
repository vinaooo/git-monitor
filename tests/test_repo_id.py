import unittest

from painel.repo_id import host_of, kind, migrate, parse, parse_account, set_forgejo_hosts


class ParseTest(unittest.TestCase):
    def test_github_forms(self):
        for text in ('https://github.com/gnome/gtk.git', 'github.com/gnome/gtk/issues?x=1', ' gnome/gtk '):
            self.assertEqual(parse(text), 'github.com/gnome/gtk', text)

    def test_gitlab_forms(self):
        self.assertEqual(parse('https://gitlab.com/g/sub/p/-/issues'), 'gitlab.com/g/sub/p')
        self.assertEqual(parse('gitlab.example.org/a/b.git'), 'gitlab.example.org/a/b')

    def test_forgejo_forms(self):
        for text in ('https://codeberg.org/forgejo/forgejo/src/branch/main/x', 'codeberg.org/forgejo/forgejo/pulls?state=open',
                     'https://gitea.example.org/a/b.git'):
            self.assertEqual(parse(text), text.split('//')[-1].split('/src')[0].split('/pulls')[0].removesuffix('.git'), text)

    def test_declared_forgejo_host(self):
        self.assertIsNone(parse('https://git.example.com/a/b'))
        set_forgejo_hosts([' Git.Example.com '])
        try:
            self.assertEqual(parse('https://git.example.com/a/b/issues'), 'git.example.com/a/b')
            self.assertEqual(kind('git.example.com'), 'forgejo')
            self.assertEqual(parse_account('git.example.com/acct'), ('git.example.com', 'acct'))
        finally:
            set_forgejo_hosts([])
        self.assertIsNone(kind('git.example.com'))

    def test_kind(self):
        self.assertEqual([kind(h) for h in ('github.com', 'gitlab.com', 'gitlab.x.org', 'codeberg.org', 'forgejo.x.org', 'example.com')],
                         ['github', 'gitlab', 'gitlab', 'forgejo', 'forgejo', None])

    def test_rejects(self):
        for text in ('https://example.com/a/b', 'foo', 'a/b/c', '', 'https://github.com/onlyone'):
            self.assertIsNone(parse(text), text)

    def test_migrate_and_host(self):
        self.assertEqual(migrate('a/b'), 'github.com/a/b')
        self.assertEqual(migrate('gitlab.com/a/b'), 'gitlab.com/a/b')
        self.assertEqual(host_of('gitlab.com/a/b'), 'gitlab.com')


class ParseAccountTest(unittest.TestCase):
    def test_github_forms(self):
        for text in ('https://github.com/vinaooo', 'github.com/vinaooo/', 'https://github.com/vinaooo?tab=repositories',
                     ' @vinaooo ', 'vinaooo'):
            self.assertEqual(parse_account(text), ('github.com', 'vinaooo'), text)

    def test_gitlab_forms(self):
        self.assertEqual(parse_account('https://gitlab.com/group/sub'), ('gitlab.com', 'group/sub'))
        self.assertEqual(parse_account('gitlab.com/someone/'), ('gitlab.com', 'someone'))

    def test_forgejo_account(self):
        self.assertEqual(parse_account('https://codeberg.org/forgejo'), ('codeberg.org', 'forgejo'))
        self.assertIsNone(parse_account('https://codeberg.org/a/b'))

    def test_bare_name_uses_default_host(self):
        self.assertEqual(parse_account('someone', 'gitlab.com'), ('gitlab.com', 'someone'))

    def test_rejects(self):
        # a GitHub repo URL is "Add repository", not an account; unknown hosts, junk and empty are not accounts
        for text in ('github.com/o/r', 'https://example.com/a', 'a/b', 'bad name', '', 'https://github.com/'):
            self.assertIsNone(parse_account(text), text)
