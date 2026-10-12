"""Importing an account's repositories as a group. Pure: the dialog and the window do the I/O."""


def group_name(account):
    """'vinaooo' -> 'Vinaooo'; a GitLab 'group/sub' -> 'Sub'."""
    last = account.rsplit('/', 1)[-1]
    return last[:1].upper() + last[1:]


def select(infos, forks, archived):
    """Keep forks / archived repos only when asked for; everything else (public and private) stays."""
    return [i for i in infos if (forks or not i.fork) and (archived or not i.archived)]


def plan(infos, host, forks, archived, tracked):
    """-> (new identities to add, how many selected repos are already tracked). Case-insensitive like 'Add repository'."""
    seen = {t.lower() for t in tracked}
    idents = [f'{host}/{i.path}' for i in select(infos, forks, archived)]
    new = [i for i in idents if i.lower() not in seen]
    return new, len(idents) - len(new)
