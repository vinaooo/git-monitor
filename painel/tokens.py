import gi
gi.require_version('Secret', '1')
from gi.repository import GLib, Secret

_SCHEMA = Secret.Schema.new('io.github.vina.Painel', Secret.SchemaFlags.NONE,
                            {'purpose': Secret.SchemaAttributeType.STRING,
                             'host': Secret.SchemaAttributeType.STRING})


class TokenStoreError(Exception):
    pass


class TokenStore:
    """Per-host access tokens in libsecret."""

    def get(self, host):
        try:
            t = Secret.password_lookup_sync(_SCHEMA, {'host': host}, None)
            if t is None and host == 'github.com':  # token saved before multi-host support
                t = Secret.password_lookup_sync(_SCHEMA, {'purpose': 'github-token'}, None)
            return t
        except GLib.Error:  # no keyring / portal denied: behave as "no token"
            return None

    def set(self, host, token):
        """Raises TokenStoreError if the keyring is unavailable; never falls back to plaintext."""
        try:
            if token:
                Secret.password_store_sync(_SCHEMA, {'host': host}, Secret.COLLECTION_DEFAULT,
                                           f'Git Monitor token for {host}', token, None)
            else:
                Secret.password_clear_sync(_SCHEMA, {'host': host}, None)
        except GLib.Error as e:
            raise TokenStoreError(str(e)) from e
