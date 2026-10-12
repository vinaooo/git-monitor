class SourceStore:
    """Groups that were imported from an account: (group, host, account, kinds, known). `known` is every repository
    seen at the last listing, so sync adds only repos that appeared since and never resurrects a card the user removed.
    Persistence is injected via `save([(group, host, account, kinds, known)])`, like `TitleStore`."""

    def __init__(self, initial, save):
        self._sources = {g: (h, a, list(k), list(kn)) for g, h, a, k, kn in initial}
        self._save = save

    def _commit(self):
        self._save([(g, h, a, k, kn) for g, (h, a, k, kn) in self._sources.items()])

    def all(self):
        return [(g, h, a, list(k)) for g, (h, a, k, _) in self._sources.items()]

    def add(self, group, host, account, kinds, known):
        old = self._sources.get(group)
        merged = list(dict.fromkeys([*(old[3] if old else []), *known]))
        self._sources[group] = (host, account, list(kinds), merged)
        self._commit()

    def take_new(self, group, listed):
        """Identities in `listed` not seen before (case-insensitive); they become known."""
        if group not in self._sources:
            return []
        host, account, kinds, known = self._sources[group]
        seen = {k.lower() for k in known}
        new = [i for i in dict.fromkeys(listed) if i.lower() not in seen]
        if new:
            self._sources[group] = (host, account, kinds, known + new)
            self._commit()
        return new

    def rename_group(self, old, new):
        if old in self._sources:
            self._sources = {(new if g == old else g): v for g, v in self._sources.items()}
            self._commit()

    def remove_group(self, group):
        if self._sources.pop(group, None) is not None:
            self._commit()
