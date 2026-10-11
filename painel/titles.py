class TitleStore:
    """Custom card titles keyed by repo identity. Persistence is injected via `save(dict)`."""

    def __init__(self, titles, save):
        self._titles, self._save = dict(titles), save

    def get(self, ident):
        return self._titles.get(ident)

    def set(self, ident, title):
        title = title.strip()
        if title:
            self._titles[ident] = title
        else:
            self._titles.pop(ident, None)  # blank = back to the repo's own name
        self._save(dict(self._titles))

    def remove(self, ident):
        if self._titles.pop(ident, None) is not None:
            self._save(dict(self._titles))
