"""Card ordering for the sort menu. Pure: works on (title, RepoStatus|None) pairs."""

_CI_RANK = {'failure': 0, 'running': 1, 'cancelled': 2, 'success': 3, 'none': 4}

# mode -> (key(title, status), natural direction is descending?)
_MODES = {
    'name': (lambda title, s: title.casefold(), False),
    'issues': (lambda title, s: s.issues, True),
    'prs': (lambda title, s: s.prs, True),
    'ci': (lambda title, s: _CI_RANK.get(s.ci, len(_CI_RANK)), False),
}


def sorted_order(order, mode, reverse, info):
    """`order` (manual order) re-sorted by `mode`. info[id] = (title, status or None).
    Repos without data yet (or whose fetch failed) go last, in manual order, in both directions;
    ties keep manual order. Name sorting needs no data, so it uses every repo."""
    if mode not in _MODES:
        return list(order)
    key, descending = _MODES[mode]
    needs_data = mode != 'name'
    known = [i for i in order if not needs_data or (info[i][1] is not None and not info[i][1].error)]
    unknown = [i for i in order if i not in known]
    # stable sort on the natural direction, then flip for `reverse` while keeping ties in manual order
    flip = descending != reverse
    known.sort(key=lambda i: key(*info[i]), reverse=flip)
    return known + unknown
