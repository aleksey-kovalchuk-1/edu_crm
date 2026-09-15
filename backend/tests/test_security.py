import base64
import hashlib

import pytest
from cryptography.fernet import Fernet

from app.security import TokenCipher, new_token, pkce_pair, safe_next_path, token_hash, tokens_match


@pytest.mark.parametrize('value, expected', [
    ('/interactions', '/interactions'),
    ('/universities?city=Москва#top', '/universities?city=Москва#top'),
    ('', '/'),
    (None, '/'),
    ('interactions', '/'),
    ('//evil.example/path', '/'),
    ('/\\evil.example', '/'),
    ('/\t/evil.example', '/'),
    ('https://evil.example', '/'),
    ('/api/v1/auth/logout', '/'),
    ('/' + 'a' * 600, '/'),
])
def test_safe_next_path(value, expected):
    assert safe_next_path(value) == expected


def test_pkce_pair_follows_rfc_7636():
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    assert challenge == expected


def test_tokens_are_unique_and_hash_is_stable():
    first, second = new_token(), new_token()
    assert first != second
    assert token_hash(first) == token_hash(first)
    assert len(token_hash(first)) == 64


@pytest.mark.parametrize('expected, provided, result', [
    ('abc', 'abc', True),
    ('abc', 'abd', False),
    ('abc', '', False),
    ('', '', False),
    ('abc', None, False),
])
def test_tokens_match(expected, provided, result):
    assert tokens_match(expected, provided) is result


def test_cipher_round_trip_and_wrong_key():
    cipher = TokenCipher(Fernet.generate_key())
    encrypted = cipher.encrypt('refresh-token')
    assert 'refresh-token' not in encrypted
    assert cipher.decrypt(encrypted) == 'refresh-token'
    assert TokenCipher(Fernet.generate_key()).decrypt(encrypted) is None
    assert cipher.decrypt('not-a-token') is None
