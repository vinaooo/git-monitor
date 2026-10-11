import unittest
from unittest import mock

from gi.repository import GLib

from painel import tokens
from painel.tokens import TokenStore, TokenStoreError


class KeyringFailureTest(unittest.TestCase):
    def test_get_returns_none_when_keyring_unavailable(self):
        with mock.patch.object(tokens.Secret, 'password_lookup_sync', side_effect=GLib.Error('no keyring')):
            self.assertIsNone(TokenStore().get('github.com'))

    def test_set_raises_domain_error_without_plaintext_fallback(self):
        with mock.patch.object(tokens.Secret, 'password_store_sync', side_effect=GLib.Error('no keyring')):
            with self.assertRaises(TokenStoreError):
                TokenStore().set('github.com', 'tok')
