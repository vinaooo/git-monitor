DEFAULT_GROUP = 'General'


class Groups:
    """Ordered named groups of repo identities; each repo lives in exactly one group.
    Persistence is injected via `save([(name, [idents])])`."""

    def __init__(self, initial, save, legacy_repos=()):
        self._groups = [(n, list(r)) for n, r in initial] or [(DEFAULT_GROUP, list(legacy_repos))]
        self._save = save

    def persist(self):
        self._commit()

    def _commit(self):
        self._save([(n, list(r)) for n, r in self._groups])

    def _index(self, name):
        return next((i for i, (n, _) in enumerate(self._groups) if n == name), None)

    def _name_free(self, name, ignore=None):
        return bool(name) and all(n.lower() != name.lower() for n, _ in self._groups if n != ignore)

    def names(self):
        return [n for n, _ in self._groups]

    def repos(self, group):
        return list(self._groups[self._index(group)][1])

    def all_repos(self):
        return [r for _, repos in self._groups for r in repos]

    def group_of(self, ident):
        return next((n for n, repos in self._groups if ident in repos), None)

    def add_group(self, name):
        name = name.strip()
        if not self._name_free(name):
            return None
        self._groups.append((name, []))
        self._commit()
        return name

    def rename(self, old, new):
        new, i = new.strip(), self._index(old)
        if i is None or not self._name_free(new, ignore=old):
            return False
        self._groups[i] = (new, self._groups[i][1])
        self._commit()
        return True

    def can_remove(self, group):
        return len(self._groups) > 1 and self._index(group) is not None

    def remove(self, group):
        if not self.can_remove(group):
            raise ValueError(f'cannot remove group {group!r}')
        _, repos = self._groups.pop(self._index(group))
        self._commit()
        return repos

    def add_repo(self, group, ident):
        if self.group_of(ident) is None:
            self._groups[self._index(group)][1].append(ident)
            self._commit()

    def remove_repo(self, ident):
        for _, repos in self._groups:
            if ident in repos:
                repos.remove(ident)
                self._commit()

    def move_repo(self, ident, group):
        if self.group_of(ident) is not None and self._index(group) is not None:
            self.remove_repo(ident)
            self.add_repo(group, ident)

    def set_order(self, group, idents):
        i = self._index(group)
        if i is not None and sorted(idents) == sorted(self._groups[i][1]):
            self._groups[i] = (group, list(idents))
            self._commit()

    def set_group_order(self, names):
        if sorted(names) == sorted(self.names()):
            by_name = dict(self._groups)
            self._groups = [(n, by_name[n]) for n in names]
            self._commit()
