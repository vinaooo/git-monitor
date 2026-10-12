"""Importing an account's repositories as a group. Pure: the dialog and the window do the I/O."""


def group_name(account):
    """'vinaooo' -> 'Vinaooo'; a GitLab 'group/sub' -> 'Sub'."""
    last = account.rsplit('/', 1)[-1]
    return last[:1].upper() + last[1:]


def wanted(info, forks, archived):
    """Forks / archived repos only when asked for; everything else (public and private) is wanted."""
    return (forks or not info.fork) and (archived or not info.archived)


def select(infos, forks, archived):
    return [i for i in infos if wanted(i, forks, archived)]


def plan(infos, host, forks, archived, tracked):
    """-> (new identities to add, how many selected repos are already tracked). Case-insensitive like 'Add repository'."""
    seen = {t.lower() for t in tracked}
    idents = [f'{host}/{i.path}' for i in select(infos, forks, archived)]
    new = [i for i in idents if i.lower() not in seen]
    return new, len(idents) - len(new)


def default_selection(infos, host, forks, archived, tracked):
    """Identities ticked in the picker before the user touches it: wanted kinds, not tracked yet."""
    return set(plan(infos, host, forks, archived, tracked)[0])
