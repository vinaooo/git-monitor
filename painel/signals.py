"""Optional card signals: ids, Preferences text, which need a token, and their extra API cost. Pure."""

# (id, title, subtitle); the GSettings key is `signal-<id>`
SIGNALS = (
    ('security', 'Security alerts', 'Open Dependabot and code scanning alerts. GitHub, token needed.'),
    ('reviews', 'Unresolved review comments', 'Unresolved threads on open pull requests. GitHub, token needed.'),
    ('release', 'Last release', 'Latest release tag and its age. GitHub.'),
    ('push', 'Last push', 'Days since the last push. GitHub.'),
)
TOKEN_ONLY = frozenset({'security', 'reviews'})  # without a token these are never requested

# Extra counted requests per repo per pass: (conditional REST, always counted) with / without a token.
# security: one code-scanning GET + a GraphQL field; reviews: nested GraphQL threads; release: one REST GET only
# without a token (a GraphQL field otherwise); push is free (a field of the repo payload).
_COST = {'security': {True: (1, 0.1), False: (0, 0)}, 'reviews': {True: (0, 0.5), False: (0, 0)},
         'release': {True: (0, 0), False: (0, 1)}, 'push': {True: (0, 0), False: (0, 0)}}


def usable(signals, token):
    """The enabled `signals` that can run with this credential."""
    return frozenset(signals) if token else frozenset(signals) - TOKEN_ONLY


def extra_calls(signals, has_token):
    """-> (conditional REST, always counted) requests per repo per pass the enabled signals add."""
    costs = [_COST[s][has_token] for s in signals]
    return sum(c for c, _ in costs), sum(f for _, f in costs)


def enabled(settings):
    return frozenset(i for i, _t, _s in SIGNALS if settings.get_boolean(f'signal-{i}'))
