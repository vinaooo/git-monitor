"""Card search: does a card match the words typed in the search bar? Pure; the window wires it to the UI."""

# bucket key -> words that find it. Same keys as chips.py `_CI` / `_PR`, worded like the chips.
_CI = {'failure': 'failing failed failure', 'running': 'running', 'cancelled': 'cancelled',
       'success': 'passing success green'}
_PR = {'changes': 'changes', 'failing': 'ci failing', 'conflict': 'conflict conflicts', 'waiting': 'waiting review',
       'approved': 'ready approved', 'draft': 'draft'}


def _words(table, counts, none):
    found = [w for key, w in table.items() if (counts or {}).get(key)]
    return found or [none]


def haystack(ident, title, status):
    parts = [ident, title]
    if status:
        parts += [status.name, status.url]
        if status.error:
            parts += ['error', status.error]
        else:
            parts += _words(_CI, status.ci_counts, 'no ci') + _words(_PR, status.pr_counts, 'no prs')
    return ' '.join(p for p in parts if p).lower()


def matches(query, ident, title, status):
    """Every whitespace-separated word of `query` must occur (case-insensitive) in the card's text."""
    words = query.lower().split()
    if not words:
        return True
    text = haystack(ident, title, status)
    return all(w in text for w in words)
