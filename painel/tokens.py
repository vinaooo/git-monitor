import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

_SCHEMA = Secret.Schema.new('io.github.vina.Painel', Secret.SchemaFlags.NONE,
                            {'purpose': Secret.SchemaAttributeType.STRING,
                             'host': Secret.SchemaAttributeType.STRING})


class TokenStore:
    """Per-host access tokens in libsecret."""

    def get(self, host):
        t = Secret.password_lookup_sync(_SCHEMA, {'host': host}, None)
        if t is None and host == 'github.com':  # token saved before multi-host support
            t = Secret.password_lookup_sync(_SCHEMA, {'purpose': 'github-token'}, None)
        return t

    def set(self, host, token):
        if token:
            Secret.password_store_sync(_SCHEMA, {'host': host}, Secret.COLLECTION_DEFAULT,
                                       f'Painel token for {host}', token, None)
        else:
            Secret.password_clear_sync(_SCHEMA, {'host': host}, None)
