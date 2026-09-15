"""Token, PKCE, CSRF and redirect helpers used by authentication."""
import base64
import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

MAX_NEXT_PATH_LENGTH = 500


def new_token(nbytes=32):
    return secrets.token_urlsafe(nbytes)


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def tokens_match(expected, provided):
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected.encode('utf-8'), provided.encode('utf-8'))


def pkce_pair():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    return verifier, challenge


def safe_next_path(value):
    """Returns the value only when it is a page path inside this application, otherwise '/' (no open redirects)."""
    if not value or len(value) > MAX_NEXT_PATH_LENGTH:
        return '/'
    if not value.startswith('/') or value.startswith('//') or value.startswith('/api/'):
        return '/'
    # Browsers drop tabs/newlines and treat backslashes as slashes, so "/\\evil.example" would leave the site.
    if '\\' in value or any(ord(char) < 0x20 or char == '\x7f' for char in value):
        return '/'
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return '/'
    return value


class TokenCipher:
    """Encrypts refresh tokens at rest so a database dump does not hand out live Keycloak sessions."""

    def __init__(self, key):
        self._fernet = Fernet(key)

    def encrypt(self, value):
        return self._fernet.encrypt(value.encode('utf-8')).decode('ascii')

    def decrypt(self, value):
        try:
            return self._fernet.decrypt(value.encode('ascii')).decode('utf-8')
        except (InvalidToken, ValueError):
            return None
